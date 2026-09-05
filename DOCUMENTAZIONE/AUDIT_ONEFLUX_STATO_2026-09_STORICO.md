# Storico ciclo audit 2026-09 — i verbali

Verbale delle sessioni chiuse. Ogni cifra qui è misurata al momento della
scrittura, col comando accanto — mai ereditata da un documento precedente.

> **Questo è l'archivio, non l'indice.** Per sapere *cosa manca* apri
> `AUDIT_ONEFLUX_STATO_2026-09.md`: è corto e si legge in un minuto.

## Indice

| Data | Sessione | Verdetto |
|---|---|---|
| 30/08 | Route API — 169 route Next | chiusa: le 3 ipotesi erano false |
| 31/08 | Voci ereditate + 1º pezzo scadenziario | 2 voci su 3 false alla ri-misura |
| 31/08 | Scadenziario (2ª sessione) | chiusa — 15/15 mutanti |
| 31/08 | `(app)/margini/` — il MOL | chiusa — 183 test, 65/65 mutanti |
| 01/09 | `(app)/catena/` — 1ª passata (3 file) | parziale |
| 01/09 | `(app)/catena/` — 2ª passata | dichiarata chiusa al 90%, **non lo era** |
| 01/09 | `(app)/catena/` — 3ª passata, export Excel | chiusa al 95% + buco nell'harness |
| 01/09 | I due bug importi, corretti su richiesta | 60 punti, non ~25 |
| 01-02/09 | Categorizzazione — fasi 0, 7, 1, 2, 3 | 5 fasi su 10 |
| 02/09 | Notifiche — un pulsante che portava nel posto sbagliato | chiusa |
| 29/08 | Punto 9 (F2-NOTEST) + voci ereditate | *spostato qui il 2/9* |
| 03/09 | Residuo R8 — guardia liste vuote catena | depennato: era già in produzione |
| 03/09 | Residuo R2 — `regen_notifiche_utente.py` | eliminato: funzione coperta dal briefing |
| 05/09 | `(app)/agenda/` + il ponte costo personale→MOL | chiusa — 6/7 mutanti, il 7° dichiarato ridondante |
| 03/09 | Residuo R3 — `card-segnali.tsx` | esclusione motivata: `catena/` al 100% |
| 03/09 | **Residuo R1 — gate mensile mobile** | **corretto: era l'unico con euro sbagliati** |
| 03/09 | Residuo R7 — letterali IVA | costante + rete: erano 29, non 4 |
| 03/09 | Residuo R4 — formattatori duplicati | 8 unificate, 8 divergono: decisione a Mattia |
| 03/09 | R4, seconda parte — decisione presa | chiuso: separatore migliaia + decimali arrotondati |
| 03/09 | **Le 3 `pct` + `catena/fatture/` letta** | chiuse; e ci è stato trovato **R10**, che mente al cliente |
| 03/09 | **R10 — il guasto travestito da «niente da fare»** | chiuso su 7 pagine cliente: 4,4 M€ non spariscono più |
| 03/09 | **R5 + R6 — le due ipotesi che non reggevano** | chiusi: nessuna sessione propria, nessuna migration |
| 03/09 | **R11 — la regola anche in SQL** | chiuso: le 7 RPC vive legate alla costante Python |

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

---

## 1-2/9/2026 — Ristrutturazione della categorizzazione: Fasi 0, 7, 1, 2, 3

Deployate l'1/9 (`e18fa37..0234da8`, 8 commit, CI verde alla prima). Cinque fasi su
dieci: restano aperte 4, 4bis, 5, 6, 8 più due voci nuove emerse strada facendo.

**Cosa cambia nel prodotto.** Il processo ha ora un solo motore di decisione
(`decisione_deterministica()`, prima la stessa scelta viveva in nove punti che potevano
divergere) e ogni riga registra **chi** l'ha classificata e **quanto** è affidabile
(`fatture.categoria_fonte` / `categoria_fiducia`). Il gate di affidabilità, che copriva
solo l'AI — il 3,6% delle righe — vale ora per tutte le fonti.

### La misura ha rovesciato il piano, per la terza volta

Il piano prevedeva un gate «il deterministico deve confermare». Simulato su 33.147
righe reali / 4,1 M€, quel criterio bocciava l'**8,6% delle righe (364.000 €)**.
Ispezionando i casi, però, sbagliava **il deterministico**, non la categoria:

- il **silenzio** del dizionario non è dubbio: `TARIFFA DI VENDITA PUN F1` → UTENZE e
  `DIVANI E ANGOLI` → MANUTENZIONE sono decisi dalla memoria e sono corretti;
- il **dissenso** non predice l'errore: su `KG5 KETCHUP` il deterministico dice
  MANUTENZIONE e SALSE E CREME è giusta; su `DOPPIO CONCENTRATO DI POMODORO` dice
  VERDURE e SCATOLAME è giusta.

È lo stesso rovesciamento già misurato sul guardrail IVA (D16) e sulla memoria globale
(D4): **la terza volta che «il deterministico è il metro» cade sotto misura.** Il
criterio adottato (conservativo, scelto da Mattia) declassa 429 righe / 38.323 € —
l'1,10% delle righe, lo 0,94% dell'importo.

### Una misura va verificata anche quando conferma ciò che si sperava

La prima cifra portata a Mattia era «280 righe / 38.193 €». Era calcolata su un campione
**troncato da un `limit 4000`**: 33.147 righe su 39.043. Il conteggio era sottostimato
del 35%; l'importo sembrava quasi giusto solo perché le righe mancanti erano di basso
valore — cioè l'errore era invisibile proprio sulla metrica che si guardava di più.
Trovato dalla code review, non da me: avevo accettato il numero perché confermava il
risultato che volevo. Cifra vera, ri-misurata sulle 6.974 combinazioni complete con
impronta verificata contro il DB: **429 righe / 38.323 €**.

### Un mutante sopravvissuto può voler dire che la riga è ridondante

Rimuovendo il reset iniziale del ContextVar in `ottieni_categoria_prodotto`, il mutante
è **sopravvissuto**. Non perché il test fosse debole: ogni uscita della funzione già
scrive la provenienza, quindi il reset non serve. Il difetto reale era il **commento**,
che lo chiamava «la parte che conta». Corretto il commento, aggiunto un test strutturale
che uccide il mutante vero (un `return` nudo che salta il canale della provenienza).

### Il gate in produzione: prima misura reale (2/9)

25 righe nuove dopo il deploy, **25 con provenienza, zero senza** — copertura 100%.
Tutte `certa`, da `L2_locale` (19) e `L1_5_non_negoziabile` (6): corretto, sono fonti
che il gate non declassa mai per regola. `da_verificare` resta 0 perché nessuna riga
con descrizione dubbia è ancora arrivata.

### Il debito che ho lasciato, e il documento che ha ingannato la sessione dopo

Ho considerato le fasi chiuse dopo mutazione, commit e review, **saltando tre dei cinque
punti di WORKFLOW §5bis**: verbale, contatore, documentazione. Avevo eseguito
`check_documentazione.py` e preso il suo verde per una prova — ma quel check non guarda
dentro `docs/piani/` e non sa cosa un documento *dovrebbe* dire.

Il costo si è visto il giorno dopo: `docs/piani/PROMPT_PROSSIMA_SESSIONE.md`, rimasto lì
stantio, dichiarava «51 commit in coda» e la Fase 3 «da fare». La sessione successiva ha
**ereditato quella cifra e l'ha riportata a Mattia**; erano 7. Il ref `origin/main` era
solo disallineato, e un `git fetch` l'ha sciolto.

Due correzioni al check, entrambe provate: `check_piani_orfani()` ora guarda **tutti** i
`.md` di `docs/piani/`, non solo `PIANO_*` — il nome di un file non è una garanzia,
conta la cartella.

### Un bug in Home trovato controllando le altre sedi (2/9)

Mattia ha chiesto di verificare il gate sui clienti che hanno righe da classificare. Il
controllo ha trovato altro: la voce «Righe classificate» della card Salute sceglieva il
testo guardando le righe caricate negli **ultimi 30 giorni** invece di quelle da
controllare (`fastapi_worker.py`). Una sede ferma da oltre un mese leggeva «Nessuna riga
da classificare» pur avendone: **4 sedi su 11**, la peggiore con 187 righe (ultimo
caricamento 21 luglio).

Il pallino e il deep-link erano corretti — mentiva solo la frase, che è l'unica cosa che
il cliente legge. Stessa classe dell'errore del 29/8: **una condizione misurata sulla
popolazione sbagliata**. Estratto `_dettaglio_righe_classificate()` come funzione pura e
coperto con 10 test; due mutanti provati, entrambi uccisi (il secondo ripristina il
ternario originale ed è fermato da una guardia strutturale).

> La lezione che vale oltre il caso: nessuno stava cercando quel bug. È emerso perché
> l'owner ha chiesto di **guardare i clienti veri** invece di fidarsi del caso singolo
> nello screenshot — dove infatti la Home diceva il vero.

## 2/9/2026 sera — Notifiche: un pulsante che non c'era, e uno che portava nel posto sbagliato

### La misura ha scelto l'area, non il prompt

Il prompt della sessione indicava di **ri-misurare la priorità invece di ereditarla**, e
la misura ha spostato la scelta due volte. Il documento di ieri escludeva l'agenda
(`turni_personale` 0 righe); contando le tabelle delle aree rimaste è emerso che
`notification_inbox` ha **67 righe, 5 utenti distinti, 5 negli ultimi 7 giorni**, con
scritture fino all'1/9. `notifiche/` era l'unica area candidata **viva**.

### Il difetto: la notifica diceva di andare in un posto, senza il modo di andarci

`ctaDi` (`lib/notifiche-shared.ts`) traduce `action_page` in una rotta Next e torna
`null` quando non sa mappare — contratto voluto: meglio nessun pulsante di un 404. Ma la
mappa conosceva solo i path Streamlit `pages/*.py`, **non i nomi di pagina**. A DB:
33 righe con `action_page='Agenda'` (topic `incasso_mancante`), scritte fino all'1/9.
La notifica «Manca l'incasso di ieri» arrivava al ristoratore **senza il pulsante**.

L'origine non era il frontend: il codice scriveva due grafie per lo stesso concetto —
`fastapi_worker.py` `/agenda` e `routers/scadenziario.py` `"Agenda"`.

> **I test c'erano già e passavano.** Coprivano `ctaDi` con input **inventati**
> (`pages/99_inesistente.py`), mai con un valore presente nel DB. Un test scritto
> guardando la mappa invece dei dati misura la mappa, non la realtà. Stessa famiglia del
> mock generoso: la copertura sembra esserci, il difetto passa.

### L'errore mio, e chi l'ha preso

La prima stesura mappava `Agenda → /agenda` e correggeva la sorgente allo stesso valore.
Il `code-reviewer` l'ha bloccata: **gli incassi non si inseriscono più in Agenda**.
`(app)/agenda/` non contiene nemmeno la stringa «incass» (i layer sono
tutto/appuntamenti/spese/personale); si inseriscono da Margini → Calcolo su desktop e da
«Movimenti» (ex Turni) su mobile.

Il pulsante sarebbe comparso — e non avrebbe fatto fare la cosa chiesta. Peggio: avrei
**creato** una divergenza dichiarando di chiuderne una, perché per lo stesso topic il
briefing (`daily_briefing_service.py`) e la notifica live (`fastapi_worker.py:5573`)
usano `/margini` da sempre.

Tre errori nella stessa stesura, tutti verificati prima di accettarli:

1. **Destinazione sbagliata** — corretta in `/margini` nei due punti.
2. **Gemello identificato male**: avevo letto `fastapi_worker.py:5385` come la versione
   giusta della stessa notifica; è `appuntamento_imminente`, un'altra. Il gemello vero è
   `:5573`, che scriveva `/margini`.
3. **Censimento incompleto**: avevo scritto «gli unici due `action_page` letterali del
   codice». Sono nove: sette stanno in `upload_handler.py:2051-2145`. L'affermazione era
   finita in una **docstring**, dove sarebbe sopravvissuta come verità.

> Il valore della review non è stato trovare un bug nel codice: è stato trovare che
> **la mia misura di partenza era giusta e la mia conclusione no**. Il dato («33 righe
> senza pulsante») era esatto; la destinazione l'ho dedotta dal nome del campo invece che
> da dove sta la funzione. Un `grep "incass"` sulla cartella costava dieci secondi.

Ripresa anche una cifra: applicando `expires_at` come fa il frontend, le righe `Agenda`
**realmente visibili** sono 3 su 2 utenti, non 11 su 3. Le altre erano già scadute.

### Cosa protegge il fix adesso

Il mutante che rimette `agenda: "/agenda"` — cioè **esattamente l'errore commesso** —
viene ucciso da un test. L'errore non può tornare in silenzio.

### La passata di copertura

Estratte da `notifiche-list.tsx` le tre funzioni pure prigioniere degli `useMemo`
(`visibili`, `contaPerFiltro`, `filtraPerSeverity`): erano già pure, ma dentro un
componente React l'harness non le raggiunge. Comportamento invariato, provato per
**oracolo** contro la versione a HEAD: 2.340 casi (severity × filtro × sottoinsiemi di
`dismissed`), 0 divergenze, **validato sui due lati** (rompendo l'oracolo: 740 e 185
divergenze — senza il secondo lato non si saprebbe se misura qualcosa).

Congelato il merge `info`+`success`: `success` **non esiste nei dati veri**, quindi
nessun dato lo proteggerebbe da una "correzione".

Mutazione: **18 mutanti, 17 uccisi**. L'unico sopravvissuto è il commento di controllo,
e doveva sopravvivere. Test del file 20 → 34. Suite 12.493 verdi, `tsc` 0, `next build`
ok, nessun drift OpenAPI.

### Quanto vale davvero il fix (il numero grande non è il beneficio)

Le righe `Agenda` a DB sono 33, ma applicando `expires_at` come fa il frontend quelle
**realmente visibili sono 3, su 2 utenti**. E la CTA compare solo sulla pagina
`/notifiche` **desktop**. Il beneficio consegnato oggi è quello: 3 avvisi su 2 clienti,
su desktop — non «11 notifiche su 3 clienti», che è il numero che avevo scritto nel
primo commit contando anche righe scadute e invisibili.

Il valore duraturo è l'altro: la sorgente non produce più il valore rotto, e il caso è
coperto da un test che uccide il ritorno dell'errore.

### Il body, riscritto tre volte

Diceva «sezione Agenda → Incassi» (sparita da mesi); l'ho corretto in «Margini →
Calcolo» — e il reviewer ha preso pure quello: `"calcolo"` è la **chiave di rotta**,
l'etichetta a schermo è «Marginalità». Di nuovo un testo scritto guardando il codice
invece dello schermo.

La terza riscrittura è arrivata col mobile, ed è la più istruttiva: il body è **uno solo
per due superfici** che ora portano in due posti diversi (Marginalità su desktop,
Movimenti sul telefono). Qualunque schermata citasse, sarebbe stata sbagliata metà delle
volte. È diventato «Usa il pulsante qui sotto», dopo aver verificato che il briefing non
lo mostra mai *senza* pulsante (scarta queste righe e le ricalcola live).

> Tre stesure per una stringa di una riga. Il testo che il cliente legge non è la parte
> facile del lavoro: nessun test lo copre, `tsc` non lo guarda, e ogni volta l'errore era
> lo stesso — descrivere il prodotto guardando il codice invece dello schermo.

### Il limite accettato è durato un'ora: l'owner ha chiesto di chiuderlo

Avevo consegnato la CTA solo su desktop, documentando il limite nel codice. Mattia ha
chiesto di farla funzionare anche dal telefono — **«ma deve andare nella sezione
corretta»**, cioè esattamente il punto dove avevo già sbagliato una volta.

Questa volta la destinazione è stata **cercata, non dedotta**: `/m/turni` è la sezione
«Movimenti» (ex Turni) e il suo tab di default è già «Incassi» (`mobile-turni.tsx`),
quindi l'utente atterra dove deve scrivere il dato senza un tocco in più. `/m/diario`
sarebbe stata la scelta "ovvia" leggendo il nome — e sarebbe stata sbagliata, perché gli
incassi ne sono usciti.

`hideCta` non spegne più tutte le CTA: `ctaMobile` rende quelle che nella PWA **esistono
davvero**. La mappa è corta di proposito — 6 sezioni mobile contro le molte rotte
desktop usate come `action_page`; `/prezzi`, `/analisi-fatture`, `/scadenziario` restano
senza pulsante, che è il motivo per cui `hideCta` esiste: un link che butta l'utente
fuori dall'app è peggio di nessun link.

Mutazione della sola parte mobile: 5 mutanti, 5 uccisi. Il primo M23 **non matchava il
sorgente** ed è stato rifatto — un mutante non applicato non prova niente.

### La seconda review: la mappa era per path, e il path non basta

Avevo mappato `/margini → /m/turni`. Il `code-reviewer` ha contato chi passa da lì: **sei
topic**, non uno. Due sarebbero finiti su un pulsante che non fa fare la cosa chiesta —
`fatturato_mancante` è il totale **mensile**, che su mobile è read-only («Totale mensile
inserito da desktop»), e `coperti_anomalia` punta a un tab `coperti` che sul mobile **non
esiste** (zero occorrenze in `(mobile)/m/`).

Era la stessa classe dell'errore `/agenda`, e il mio commento nel codice la mascherava:
diceva «contiene solo le destinazioni che sul mobile esistono davvero» — vero per il
path, falso per i topic che ci transitano. **Il commento prometteva più di quanto il
codice mantenesse.**

Ora si mappa il **topic**: `TOPIC_TO_MOBILE` ha una sola voce, `incasso_mancante`. I
mutanti che rimettono il criterio per path (M24) o aggiungono `fatturato_mancante` (M28)
vengono uccisi da un test.

### Il body persistito non arriva a schermo — e nemmeno il mio `action_page`

Verificato leggendo `get_notifiche` (`fastapi_worker.py:2748`): le righe persistite dei
topic in `_LIVE_TOPICS_DATI_MANCANTI` — `incasso_mancante` incluso — vengono **rimosse** e
sostituite dalla versione live, che ha `body: ""` e già `action_page: "/margini"`.

Quindi la riscrittura del body era corretta ma **senza effetto osservabile**, e il fix
alla sorgente conta per coerenza, non per ciò che il cliente vede oggi. Ciò che il
cliente vede è la CTA: provata sulla riga live vera, `ctaDi → /margini` e
`ctaMobile → /m/turni`. È annotato nel codice, così nessuno spende tempo a «sistemare»
un testo invisibile.

### L'aritmetica: il reviewer aveva ragione, io no

Avevo scritto totale **52.960**; la misura giusta è **52.962**. Il mio conteggio sommava
i file uno per uno e **perdeva 2 righe** su quelli senza newline finale. Riallineata anche
la *colonna* della riga `lib/`, ferma da tre giri a `2.192 | 5.290` mentre la prosa nella
stessa cella diceva altro: chi legge la tabella per colonna prendeva il numero vecchio.

---

## 29/08/2026 — Punto 9 (F2-NOTEST): i test frontend, e le voci ereditate

> Spostato qui dal file di stato il 2/9/2026, nel riordino. Era rimasto in
> cima alla roadmap per cinque giorni, occupando ~200 delle sue 437 righe:
> è un verbale, non uno stato. Il contenuto è quello originale.

## 🟢 Punto ereditato — CHIUSO il 29/08/2026

> **Mergiato e deployato la notte del 29→30/8/2026** (00:27 e 00:29 ora cliente,
> dentro la finestra consentita). PR #55 (test, nessun deploy) e PR #56
> (estrazione F7, deploy Vercel `success` alle 00:30). Merge commit `62d7593` e
> `0ed4fff`. Produzione verificata dopo il deploy: `/catena` redirige
> correttamente a `/login?next=/catena`, login 200.

**F2-NOTEST — nessun test runner frontend.** Deciso e implementato: **opzione A**
(test in `tests/*.py` che eseguono il TypeScript vero con node), non un runner
dedicato. Materiale preparatorio, archiviato col ciclo:
`docs/storico/AUDIT_ONEFLUX_STATO_2026-08_PUNTO_9.md` e `..._PUNTO_9_PROMPT.md`.

### Perché A e non Vitest

Ragione strutturale, non di gusto: `deploy-vercel.yml` scatta su `push: main`
con `paths: apps/web/**`, e non esiste `vercel.json` né `ignoreCommand`. Un
runner in `apps/web/package.json` significa che **ogni** merge di un test fa
partire un deploy di produzione: «ho cambiato un test» diventa indistinguibile
da «ho cambiato l'app». I test in `tests/` il workflow li ignora per costruzione.

Playwright (C) è stato escluso su un criterio preciso, non sul costo generico:
**non avrebbe preso nessuno dei due difetti di riferimento**. F1 produce una UI
plausibile ma sbagliata (serve un oracolo che l'E2E non ha) e F7 richiederebbe
500 descrizioni reali su account catena.

### La tecnica è cambiata: import vero, non regex

I due test storici estraevano una funzione con un regex e ne spogliavano la
firma con una `.replace()` letterale — che se la firma cambia **non fallisce**,
restituisce il sorgente invariato e node muore con un SyntaxError fuorviante. E
non attraversava gli `import`: per questo `categorie-spesa.ts`, che importa
`@/lib/admin`, era irraggiungibile.

Ora `tests/helpers_ts.py` importa il modulo di produzione vero con
`node --experimental-strip-types` + `module.registerHooks` per l'alias `@/`.
Verificato su **v22.15.0, v22.23.2** (ciò che `node-version: '22'` risolve) e
v24.19.0. Zero dipendenze npm, zero modifiche a CI/`pytest.ini`/`package.json`.

### Il risultato che ha deciso il design dei test

Prima di scrivere il test l'ho mutato: con fixture "ovvie" su `computeKpi`
(una scaduta nel 2020, una pagata, una nota di credito), **su 4 mutanti ne
moriva uno solo**. Sopravvivevano `scad < today`→`<=`, il filtro sul mese
corrente rimosso, e `new Date()` al posto di `parseLocalDate`. Un test dall'aria
del tutto sensata sarebbe entrato in CI verde coprendo quasi niente — esattamente
la «rete che sembra esserci e non c'è».

Con fixture **ai confini e relative a oggi** muoiono tutti e 6 i mutanti provati.
Ma il mutante del fuso muore **solo** con `TZ` a ovest di Greenwich: misurato,
con `Europe/Rome` sopravvive e con `Pacific/Kiritimati` (UTC+14) pure. Da qui la
parametrizzazione su `{Europe/Rome, America/Los_Angeles}` — Los Angeles non è un
fuso a caso e non è ridondante, ed è scritto nel docstring perché al primo
refactor nessuno lo tolga.

### Cosa c'è ora

| File | Contenuto |
|---|---|
| `tests/helpers_ts.py` | `esegui_ts()` + `node_o_fallisci()` (era duplicato nei 2 test storici) |
| `tests/test_categorie_spesa_frontend.py` | 43 test — F1, con **oracolo Python** (`_tipo_da_categoria`) |
| `tests/test_scadenziario_kpi_frontend.py` | 19 test — `computeKpi`/`bucketizeDocumenti`/`parseLocalDate`/`todayLocalIso`, confini + fusi |

### Cosa ha trovato il `code-reviewer` (e che è stato corretto)

Il gate ha trovato **un test che non asseriva quello che dichiarava**, esattamente
la classe di difetto che questo lavoro esiste per prevenire:

- `test_le_note_di_credito_non_sono_debiti` asseriva `1280 not in (k[c],)`, cioè
  che nessun totale valesse *esattamente* l'importo della nota di credito. Ma una
  NC che entra in un secchio ci entra **sommata**: col mutante che toglie
  l'esclusione, `da_pagare_totale` diventa 1590 e la riga passava lo stesso.
  Riscritta come confronto col campione privato della NC: ora fallisce da sola.
- `parseLocalDate` e `todayLocalIso` erano usate ma mai testate direttamente
  (`todayLocalIso` scrive `pagata_at` in produzione e ha già avuto un bug di
  fuso). Aggiunti i test; il mutante `getUTCDate()` richiede fusi agli estremi
  (`Pacific/Midway` −11, `Pacific/Kiritimati` +14) perché con i soli Rome/LA
  passerebbe o no **a seconda dell'ora in cui gira la suite**.
- Il confine dei 30 giorni era asserito solo dentro una somma, dove uno
  spostamento fra `mese` e `oltre` si compensa: ora i due bucket sono asseriti
  separatamente.
- La guardia anti-F1 non vedeva un array di oggetti né una union di tipi (la
  regex non attraversa l'annidamento). Riscritta su un criterio più semplice —
  il file nomina le 4 generali e **nessuna** F&B — e verificata contro tutte e
  tre le forme.

**E una CI rossa**: `test_i_kpi_non_dipendono_dal_fuso` confrontava tutti i KPI
di un campione unico valutato in due fusi. Ma fra le 22:00 e le 00:00 UTC Roma e
Los Angeles sono in **due giorni diversi**, quindi un documento «scade oggi» è
già scaduto per l'uno e non per l'altro — per costruzione, senza che il codice
abbia niente che non va. Il test era rosso ~2 ore su 24, e la «mitigazione» che
avevo scritto (ricostruire sul fuso più indietro) spostava il buco invece di
chiuderlo, perché il campione veniva poi valutato in entrambi. Riscritto: si
confrontano solo i KPI delle **pagate**, dove `pagata_at` è una data nuda che
vale lo stesso giorno ovunque. I bucket di scadenza dipendono legittimamente dal
"today" locale e non vanno confrontati fra fusi.

Mutanti provati in totale: **9**, tutti uccisi. Due erano stati "provati" con un
pattern che non matchava il sorgente: non applicavano nessuna mutazione, e il
loro "sopravvissuto" non voleva dire niente. Ri-eseguiti sul codice vero.

Il confronto di F1 è **comportamentale**, categoria per categoria, non fra
costanti: leggere due liste passerebbe anche se `tipoDaCategoria` invertisse il
ramo (provato: invertendolo cadono 38 test). Più una guardia che impedisce a F1
di riformarsi — cerca un file che *riderivi la divisione* FB/generali, non che
nomini qualche categoria: la prima stesura segnalava `admin.ts` (le 29
canoniche), `periodi.ts` (mappa di icone) e `demo-data.ts` (righe finte), tutti
legittimi. Ricreando il difetto la guardia scatta.

### Cosa NON copriamo — dichiarato

Rendering React, hook, stato, effetti, `useMemo`, routing, CSS, accessibilità,
integrazione API reale, e tutto ciò che sta fuori da `lib/` (~47.500 righe).
Copriamo **logica pura in moduli senza React**.

**`poolSaturo` (F7): coperto, in una PR separata.** Viveva dentro un `useMemo`
anonimo in `gruppo-tag-section.tsx`, dove nessuna tecnica lo raggiungeva.
Estratto in `apps/web/src/lib/tag-candidati.ts` (`calcolaCandidati`), con
`RPC_LIMITE_DESCRIZIONI` allineata al `p_limit` di `routers/gruppo.py` — non è
la «fonte unica»: il 500 vive in **tre** posti indipendenti (il router, il
DEFAULT della funzione SQL, la costante client), e un test confronta il valore
client col router perché la divergenza non resti invisibile. 12 test, e **reintrodurre il difetto originale
(`pool.length` invece di `risposta.length`) li fa fallire**.

Il refactor è provato equivalente, non solo `tsc`-pulito: vecchia e nuova
implementazione confrontate su **504 combinazioni** di pool/associate/filtro
(0 divergenze). Tenuto in una PR separata perché tocca `apps/web/**` e quindi
fa partire il deploy Vercel.

Resta scoperto, e dichiarato nel docstring del test: che il *componente* passi
`risposta` e non il pool filtrato. Il componente non è testato (nessun
rendering). Mitigazione a costo zero: il parametro si chiama `risposta`, è il
primo, e nel componente non esiste più una variabile filtrata prima della
chiamata.

### Correzione al documento preparatorio

Il dossier citava `margini.ts` come «dove sta il calcolo dei
numeri del cliente»: **falso**, contiene solo tipi e wrapper `fetch`, il calcolo
è server-side. Gran parte di `lib/` è così — la superficie di logica pura reale è
ben minore delle 3.339 righe. Corretto nel documento.

Le altre cifre del documento sono state ri-misurate e reggono tutte: 399 file,
50.891 righe, 3.339 in `lib/`, zero runner, 55 test node preesistenti.


### Le tre voci ereditate, ri-misurate il 31/08 — 2 su 3 erano false

## Voci aperte ereditate — ri-misurate il 31/08/2026: 2 su 3 erano false

> **Lezione, non contabilità.** Queste tre voci erano marcate «verificate ancora
> vere il 30/8/2026». Ri-misurate il 31/8 **una per una col comando accanto**,
> due non reggono. Erano già state riprese per buone all'inizio della sessione
> del 31/8 e hanno prodotto lavoro fantasma finché la misura non le ha smontate:
> è esattamente il modo in cui un documento sempre in contesto propaga i propri
> errori. Restano scritte qui, smentite e non cancellate, perché la smentita
> vale più della voce.

1. ~~**Il blocco notifiche `source_type='upload'` è morto.**~~ **FUORVIANTE.**
   Non è codice morto: è **irraggiungibile per costruzione**, ed è già
   documentato nel repo. Le 7 `build_notification_record`
   (`upload_handler.py:1987-2080`) vivono dentro `handle_uploaded_files`
   (`:897`), il cui **unico** chiamante è `legacy_streamlit/app_controllers.py:1701`
   — modulo che importa `streamlit` vero, **non installato** (vedi CLAUDE.md e
   `services/_streamlit_shim.py`). Il blocco legge
   `st.session_state.get('ristorante_id')`: sullo shim è un dict vuoto, quindi
   `_inbox_rid` resta `""` e la guardia `if _inbox_uid and _inbox_rid` non passa
   mai. **La data «1/6/2026» non è un guasto da indagare: è la dismissione di
   Streamlit.** Cinque test lo dichiarano già escluso per misura
   (`test_radar_aggancio_percorso_vivo.py`, `test_invoice_vision.py`,
   `test_td24.py`, `test_upload_handler_pagination.py`, `upload_policy.py:4`).
   Nessuna azione: lo stato è già scritto dove serve, cioè nel codice.

   ```bash
   grep -rn "handle_uploaded_files" --include=*.py . | grep -v tests/
   ```

2. ~~**`check_weekly`** — zero chiamanti, da agganciare o rimuovere~~
   **CHIUSA il 31/08/2026: la domanda era mal posta.** Zero chiamanti confermato,
   ma agganciarlo **non produrrebbe nulla**: è una **catena morta a due anelli**.
   `check_weekly` legge `notification_inbox` con `topic_key='price_alert'`, e
   l'unico emettitore di quel topic è `upload_handler.py:2019` — dentro
   `handle_uploaded_files`, cioè il percorso `legacy_streamlit` già dichiarato
   morto. Sul DB live: **3 righe `price_alert`, tutte `source_type='upload'`,
   l'ultima 1/6/2026** (la dismissione di Streamlit).

   Quindi schedularlo domani leggerebbe 0 righe e tornerebbe `[]` per sempre.
   **Né agganciato né rimosso**: la logica (`fornitore_critico_consecutivo`) è
   scritta e testata, manca il *produttore* a monte. Il radar vivo
   (`check_on_upload`) oggi emette altri tre topic.

   Non è più una voce di roadmap perché **il fatto è ora nel codice e in una
   rete**: docstring di `anomaly_radar_service.py` + 2 test in
   `test_radar_aggancio_percorso_vivo.py` (via **AST**, non match testuale) che
   falliscono se qualcuno aggancia `check_weekly` **o** se nasce un sorgente
   nuovo di `price_alert` — nel secondo caso la notizia è buona, e la decisione
   va ripresa. I due sorgenti noti (`upload_handler.py`, percorso legacy; e
   `fastapi_worker.py:6443`, dict in memoria che non persiste) sono in allowlist
   con la loro ragione.

   ```sql
   SELECT topic_key, source_type, count(*), max(created_at)::date
   FROM notification_inbox GROUP BY 1,2 ORDER BY 3 DESC;
   ```

3. ~~**`normalizza_descrizione`** — 5 pattern su 7~~ **FALSO.** La funzione
   (`utils/text_utils.py:115`) applica **tutti e 7** gli step, e tutte e sei le
   costanti `REGEX_*` che usa esistono, sono importate (`:17-22`) e sono
   popolate: `REGEX_UNITA_MISURA` 30 pattern, `REGEX_SOSTITUZIONI` 19,
   `REGEX_ARTICOLI` 10, più tre regex singole. Nessun residuo del ciclo 2026-07.
   **Voce chiusa.**

   ```bash
   python3 -c "import utils.text_utils as t; print(len(t.REGEX_UNITA_MISURA), len(t.REGEX_SOSTITUZIONI), len(t.REGEX_ARTICOLI))"
   ```

**Baseline radar da sorvegliare**: `notification_inbox` ha **0 record
`source_type='radar'`** su 65 totali (30/8). Il radar è stato ricollegato il
29/8: dopo i primi upload reali dovrebbero comparirne **pochi e veri**. Se ne
compaiono molti, la ritaratura su `numero_documento` va rivista — prima del fix
ne avrebbe prodotti 897, tutti falsi.

---

## Residuo R8 — la guardia c'era già — 03/09/2026

**Esito: depennato, non implementato.** Il residuo chiedeva una guardia sulle
liste vuote di `config-assistente-catena.tsx`. **Era già in produzione**, messa
dal commit `71ac3ab` — cioè dalla **stessa 3ª passata su `catena/` che la
dichiarava aperta**. Il residuo è stato copiato dalla sezione «non fatto» del
verbale senza ri-guardare il codice: la lista invecchia in entrambe le
direzioni, come `parseImportoIt`.

**Cosa difende, misurato.** Lo stato iniziale di `segnali`/`pv` è `[]`, e `[]` è
anche il payload legittimo di «non ho escluso niente»: indistinguibili. Salvare
su un load fallito riattiva in silenzio le esclusioni dell'utente. La difesa è in
**due** punti che nessun test legava:

1. `caricaConfig().catch` → `setLoadError(true)`;
2. `<Button onClick={salva} disabled={saving || loading || loadError}>`.

Non la difendono `segnaliDisattivati`/`pvEsclusi`: su `[]` ogni loro mutazione dà
`[]` — mutante **impossibile**, non sopravvissuto.

**Prova per mutazione** (copia in scratchpad, mai sul file di lavoro; ogni
mutante verificato come realmente applicato prima di eseguirlo):

| Mutante | Esito |
|---|---|
| via `setLoadError(true)` dal `.catch` | ucciso |
| via `loadError` dal `disabled` del Salva | ucciso |
| stato iniziale ≠ `[]` | ucciso |
| `// setLoadError(true)` **commentato** | ~~sopravvissuto~~ → ucciso |
| `disabled={... \|\| (false && loadError)}` | ~~sopravvissuto~~ → ucciso |

**3 su 3 con i mutanti scelti da me, 3 su 5 con quelli del code-reviewer.** I due
sopravvissuti erano della classe più naturale: **neutralizzare senza rimuovere il
testo**. Cercare una sottostringa nel sorgente non distingue il codice vivo da
quello commentato o spento da un `false &&`. Corretti: il test ora scarta le
righe commentate e assicura la **forma esatta** della condizione. Rete:
`tests/test_catena_config_guardia_salva.py` (3 test); area catena verde.

**Limite dichiarato.** È una fotografia **strutturale**: prova che i due presidi
esistono e sono collegati, non che React li renderizzi — `esegui_ts` non entra
nei `.tsx`. Estrarre il `disabled` in `lib/` sarebbe indirezione inventata per il
test. Stessa scelta di `test_il_dialog_hardcoda_ancora_le_aliquote`.

**Perimetro non coperto, verificato a codice:** una `200` con liste vuote
lascerebbe il Salva abilitato. Oggi **irraggiungibile** — `_resolve_gruppo`
(`services/routers/gruppo.py:674`) solleva 400 sotto le 2 sedi e `segnali` nasce
da `_SEGNALI_CATALOGO`, mai vuoto. A DB: 2 righe `gruppo_assistant_config`,
**0 con esclusioni** — nessun danno possibile oggi.

---

## Residuo R2 — `regen_notifiche_utente.py`: eliminato — 03/09/2026

**Scelta: eliminare, non riparare.** Ripararlo avrebbe voluto dire **scrivere
codice nuovo** per uno script che nessuno usa.

**Perché era irreparabile così com'era:** importa `services.notification_service`
(riga 17) — modulo inesistente — e da lì le funzioni
`build_monthly_data_notifications` e `build_scadenza_documents_notifications`,
che **non esistono in nessun punto del repo** (grep su tutti i `.py`): sparite
con Streamlit il 17/7. Il commento a riga 27 rimandava a
`components/notifications_panel.py`, percorso anch'esso rimosso.

**Verificato eseguendolo**, non leggendolo:

```
ModuleNotFoundError: No module named 'services.notification_service'   (riga 17)
```

**Perché eliminare era la risposta giusta.** La sua funzione è coperta dal
pipeline vivo: i 4 topic che rigenerava sono prodotti da
`daily_briefing_service.py`, che gira in automatico. A DB (03/09):

| topic | righe | ultima |
|---|---|---|
| `scadenza_superata` | 5 | 01/06 |
| `costo_personale_mancante` | 3 | 05/06 |
| `fatturato_mancante` | 3 | 05/06 |
| `scadenza_imminente` | 2 | 01/06 |

Lo scopo dichiarato («allineare un utente di test senza aspettare il giro
automatico») non giustificava di riscrivere due builder scomparsi per duplicare
un servizio che già gira.

**Un motivo in più, emerso leggendolo:** lo step 1 fa una **DELETE** su
`notification_inbox` *prima* di chiamare le funzioni assenti. Riparare il solo
import avrebbe prodotto uno script che cancella le notifiche e non sa
rigenerarle. Era peggio di codice morto.

**Nessun riferimento** nel repo oltre alla riga di roadmap, ora depennata. Se
servisse di nuovo, sta in git history (`ca2d3c8`).

---

## Residuo R3 — `card-segnali.tsx`: esclusione motivata — 03/09/2026

**Esito: `catena/` chiusa al 100% del perimetro testabile**, senza forzare un
test inutile. Le 110 righe sono state rilette una per una: «fetch + JSX» è
esatto. I tre candidati all'estrazione non sopravvivono all'esame:

1. `ICONA[s.tipo] ?? AlertTriangle` — lookup su 4 chiavi, nessun ramo; il valore
   è un componente React, non asseribile in `lib/` senza renderizzare;
2. la guardia anti-race `my === reqRef.current` — vive su `useRef`: estrarla
   sarebbe indirezione creata per il test, non per il prodotto;
3. `loadError && !data` — è rendering, già coperto dall'esclusione strutturale
   del React (nessun runner in `apps/web/`, o `deploy-vercel.yml` deploya).

**Ma una rete serviva lo stesso**, e non sulla logica: la card esiste per
avvisare, e la regressione che conta è che un errore diventi silenzio
rassicurante. Il sorgente lo dichiara in un commento; un commento non è un
presidio. `tests/test_catena_card_segnali_esclusione.py` (4 test) lo lega.

**Prova per mutazione** (copia in scratchpad, ogni mutante verificato come
applicato prima di eseguirlo):

| Mutante | Esito |
|---|---|
| rami invertiti: l'errore mostra «Tutto sotto controllo» | ucciso |
| «Riprova» non richiama `carica` | ucciso |
| via una delle 3 guardie anti-race | ucciso |
| aggiunto un `.sort()` (logica che qui non deve stare) | ucciso |
| `false && loadError && !data` (ramo spento) | ~~sopravvissuto~~ → ucciso |

**4 su 4 con i miei mutanti, 4 su 5 con quelli del code-reviewer:** anche qui il
ramo *neutralizzato* passava. Corretto con lo stesso metodo di R8. L'ultimo dei
miei è il guardiano dell'esclusione: se qualcuno mette un calcolo in questo file,
l'esclusione decade e il test lo dice.

**Cifre ri-misurate — e la mia prima misura era sbagliata.** Avevo scritto
**2.938 righe** usando `cat catena/*.tsx | wc -l`: quel glob **non entra nelle
sottocartelle** e si perdeva `catena/fatture/page.tsx` (77 righe, mai lette).
La cifra vera è **2.971** (`git ls-files ... | xargs wc -l`), e l'area è al
**97%**, non al 100%: le 77 righe restano scoperte. Trovato dal code-reviewer.
I test dell'area sono **290** (il contatore diceva 283). Le «138 righe scoperte»
del vecchio contatore non corrispondono a nessun raggruppamento riproducibile.

---

## Residuo R1 — il gate mensile del mobile — 03/09/2026

**Esito: corretto.** Era l'unico residuo che produceva euro sbagliati.

**La premessa del residuo era già superata.** Diceva «quando arriveranno gli
incassi»: gli incassi **ci sono già**. A DB il 03/09: **1.049 righe** in
`ricavi_giornalieri` su **6 sedi**, ultimo dato il 02/09, più **17 override
mensili** su 4 sedi.

**Due difetti, non uno.** `mobile-incassi.tsx` riscriveva a mano la regola di
`fetchNettoMese` invece di chiamarla:

1. **riga 274** — `nettoAutorevole?.netto ?? risposta?.totale_netto ?? 0`: la
   catena di `??` schiacciava `null` («non lo so») su `0` («zero incassi»). Il
   KPI mostrava **0,00 €** su una lettura fallita.
2. **il `catch`** — su risposta non-2xx il `throw` saltava `setNettoAutorevole`:
   lo stato restava quello del **mese precedente**. Cambiando mese durante un
   disservizio si leggeva il netto di un altro mese, senza avviso.

**Il fix non riscrive la regola: la chiama.** `fetchNettoMese(a, m + 1)` dentro
la `Promise.all`, e la logica di visualizzazione estratta in
`lib/ricavi-netto-mese.ts` (`nettoDaMostrare`, `dettaglioNettoMese`) perché
`esegui_ts` non entra nei `.tsx`. Il round-trip risparmiato dalla versione
precedente costava la distinzione null/zero: il commento ora lo dice.

**Provato eseguendo, non compilando** (`tsc` passa anche sul difetto). Le due
funzioni concatenate come le concatena il componente, sui valori veri di giugno:

| scenario | netto | a schermo |
|---|---:|---:|
| override mensile | 73.322,73 | `73322.73 EUR` |
| solo giornalieri | 3.227,27 | `3227.27 EUR` |
| mese davvero a zero | 0 | `0.00 EUR` |
| **lettura fallita** | `null` | **`—`** |

Il ramo sbagliato su giugno valeva **70.095 €** di differenza.

**Mutazione:** 4 mutanti su `lib/ricavi-netto-mese.ts`, **4 uccisi** — il primo è
il difetto originale (`?? 0`), che fa cadere 3 test. Rete:
`tests/test_mobile_incassi_netto_frontend.py` (14 test); regressione 231 test
verdi su margini/ricavi/format.

---

## Residuo R7 — i letterali IVA — 03/09/2026

**Esito: costante nominata in `margine_service.py` + una rete su tutto il resto.**

**Il residuo sottostimava il problema di sei volte.** Diceva «4 letterali in
`margine_service.py`». Misurati il 03/09 col `grep` sull'intero backend: **29
occorrenze in 5 file**.

> **Come si contano, perché sbagliarlo è facile.** `grep -c` conta le **righe**,
> non le occorrenze, e molte righe ne portano due (`/1.10` e `/1.22` nella stessa
> espressione). A righe sembrano 18; contate davvero sono 29. La prima cifra che
> avevo scritto era 18: **l'ha corretta il test**, non io.

| file | occorrenze |
|---|---:|
| `services/fastapi_worker.py` | 10 |
| `services/routers/ricavi.py` | 6 |
| `services/routers/gruppo.py` | 5 |
| `services/routers/margini.py` | 4 |
| `services/margine_service.py` | 4 → **0** |

**Scelta dell'owner:** sostituire solo in `margine_service.py` (il perimetro del
residuo) e **legare le 25 restanti con un test**, invece di toccare 5 moduli che
calcolano il MOL su tutto lo storico in una sessione con altri punti aperti.
Stesso metodo di `test_margini_iva_equivalenza_frontend.py`, che sulla stessa
classe di problema ha scelto la rete e non il refactor di massa.

**Il MOL non si è spostato di un bit.** Verificato eseguendo `calcola_risultati`
su 7 casi (0, negativi, decimali, i valori veri di giugno) e confrontando col
risultato della formula a letterali: identico su tutti, `80.655 → 73.322,73 €`.

**Mutazione** — 4 mutanti, **4 uccisi**, i due che contano davvero in cima:

| Mutante | Esito |
|---|---|
| aliquota cambiata **solo in Python** | ucciso |
| aliquota cambiata **solo in TypeScript** | ucciso |
| `margine_service` torna ai letterali | ucciso |
| copia **nuova** in un router | ucciso |

Rete: `tests/test_iva_divisori_fonte_unica.py` (9 test). Regressione: **667 test**
verdi su margini/ricavi/IVA.

**Perimetro dichiarato, non taciuto:** restano **25 occorrenze** in 4 file, ora
fotografate una per una — di cui **3 in commenti/docstring** (`routers/gruppo.py`
righe 205 e 567): il perimetro da migrare davvero è ~22, e la distinzione è
scritta nel test perché un numero gonfiato è l'errore opposto ma della stessa
famiglia di quando le 29 erano state contate 18 (code-reviewer, 3/9). **Nessuna
divergenza attiva oggi:** tutte le 25 valgono `1.10`/`1.22`, coerenti con le
costanti e con `periodi.ts`. Se diminuiscono qualcuno sta migrando; se aumentano è
una copia nuova, ed è così che da 4 sono diventate 29.

---

## Residuo R4 — formattatori duplicati: unificate 8, le altre 8 divergono — 03/09/2026

**Esito: metà chiusa, metà portata a Mattia.** Il residuo lo prevedeva
(«unificarli cambia cosa il cliente vede»): il test di equivalenza ha detto
**quali** si potevano toccare, e ha impedito due sostituzioni sbagliate.

**Unificate (output identico, provato byte per byte):**

- **4 copie di `MESI`/`MESI_LABEL`** → `MESI_LUNGHI` di `lib/mesi.ts`;
- **4 copie di `euro`** → `formatEuro` di `lib/format.ts`. Le due
  implementazioni erano scritte in modo diverso (`Intl.NumberFormat` contro
  `toLocaleString`) e danno la **stessa stringa** su tutti i casi: verificato,
  non dedotto dalla somiglianza.

−45 righe, +9. `catena/` verde, 610 test.

**NON unificate, perché divergono davvero:**

| Funzione | divergenza misurata |
|---|---|
| le 2 `euro2` | **sempre**: `Intl` mette U+00A0 prima di €, `toFixed` uno spazio normale. Da 5 cifre in su si aggiunge il separatore delle migliaia (`12.345,60` vs `12345,60`) |
| le 2 `num` | decimali: `1234,6` (max 1) contro `1234,567` (default) |
| le 3 `pct` | **`formatPct` di `lib/` non è sostituibile**: usa `toFixed`, non `toLocaleString`. Diverge su *tutti* i casi — `12.3%` invece di `12,3%` (punto al posto della virgola), `0.0%` invece di `0%`, e arrotondamento diverso (`12.35` → `12,4%` vs `12.3%`) |

**Il test ha impedito un difetto, non solo documentato uno.** Sostituire `pct`
con `formatPct` sembrava la stessa pulizia di `euro` — le firme si somigliano.
Avrebbe messo il **punto decimale in ogni percentuale italiana** di catena.

**Una mia affermazione corretta dalla misura:** avevo scritto che `Intl` separa
le migliaia a `1.234,56`. È falso — la locale italiana non separa a 4 cifre; il
separatore compare da 10.000. La divergenza sotto quella soglia è **solo** lo
spazio.

**Mutazione:** 3 mutanti, **3 uccisi** (un mese alterato, `formatEuro` con altri
decimali, `formatPct` allineato). Il terzo è il guardiano della fotografia: se
qualcuno *risolve* la divergenza, il test lo dice invece di invecchiare in
silenzio. Rete: `tests/test_catena_formattatori_equivalenza_frontend.py`
(17 test).

**Decisione che resta a Mattia:** quale forma è quella giusta per `euro2`, `num`
e `pct`. Sono 8 copie e tre domande di prodotto, non di codice.

---

## R4, seconda parte — la decisione di Mattia — 03/09/2026

**Esito: R4 chiuso.** Portata la divergenza, Mattia ha deciso: **separatore delle
migliaia e decimali arrotondati**.

| Copia | Prima | Dopo |
|---|---|---|
| `euro2` in `finestra-margini-coperti` | `12345,60 €` | **`12.345,60 €`** |
| `num` in `finestra-margini-coperti` | `1234,567` (3 dec) | **`1234,6`** (1 dec) |

Entrambe le `euro2` ora chiamano `formatEuro(n, 2)` — verificato identico
byte per byte alla forma `Intl` su 12 casi prima di sostituire. La guardia sul
null resta: `—`, non `0,00 €`.

**Le 3 `pct` restano duplicate**, e non è un residuo lasciato aperto:
`formatPct` di `lib/format.ts` usa `toFixed` e produrrebbe `12.3%` invece di
`12,3%`. Unificarle richiede prima di correggere `formatPct`, che ha altri
chiamanti fuori da `catena/`.

**Un errore mio, trovato da `tsc`.** Avevo classificato `euro`, `pct` e `num` di
`finestra-margini-coperti` come **codice morto** e le avevo eliminate: il mio
`grep -c "[^a-zA-Z_]pct("` cercava la parentesi di chiamata, ma quelle funzioni
sono passate **per riferimento** nella tabella `COLS` (`fmt: pct`). Sono le
colonne Margine %, Fatturato, Coperti, Scontrino medio, €MP/coperto — vivissime.
Ripristinate. *Un grep che cerca la forma sbagliata non dice «non c'è»: dice che
non l'ha vista.*

**Mutazione:** 2 mutanti, il primo ucciso subito, **il secondo sopravvissuto** e
poi ucciso. `num` riportata a 3 decimali passava indenne: il test *ricostruiva*
l'implementazione e la eseguiva, provando che quella forma arrotonda — non che il
file la usi. Aggiunto il test che legge il sorgente vero. È la stessa classe di
buco trovata dal code-reviewer sui presidi di R8 e R3.

Rete: `tests/test_catena_formattatori_equivalenza_frontend.py` (24 test).

---

## 03/09 — Il gate di review contava il lavoro delle altre sessioni

**Verdetto:** chiusa. Difetto di processo, non di prodotto: nessun numero cliente
cambia.

**Fatto**
- Il gate Stop misurava `git diff <merge-base con origin/main>`: **tutti** i
  commit non pushati, di qualunque sessione. Ora restringe la base ai commit
  della sessione corrente (`timestamp_avvio` dal registro + `session_id` dal
  payload, che il gate scartava).
- Degrado sempre verso il comportamento storico — registro assente, sessione non
  registrata, payload malformato → merge-base come prima. **Mai verso il
  silenzio.**
- Corretta la voce del MEDIUM catena-tag: dichiarato aperto a 236,23 €, era
  **chiuso dal 27/8**. Corretto alla fonte (il prompt archiviato) e in roadmap.

**Trovato — tre difetti che nessuno cercava**
- Una **tolleranza di 120s** sull'avvio, messa per prudenza, faceva rientrare il
  commit appena chiuso da un'altra sessione: l'errore da eliminare. Rimossa.
- Ricadere su `"HEAD"` quando nessun commit è attribuibile rendeva il gate
  **muto**: git ha risoluzione al secondo, e una sessione che committa nello
  stesso secondo in cui parte misura zero. Cieco su 9 file di codice.
- **Il marker anti-loop era condiviso** (chiave: solo HEAD). Con la base ormai
  per-sessione, la prima che segnala zittisce la seconda. Trovato dal
  `code-reviewer`, riprodotto: A avvisata su 18 file, B con 7 file propri →
  silenzio.

**Non fatto, e dichiarato**
- L'attribuzione è per **finestra temporale, non per autore**: include ciò che
  altri committano dopo l'avvio della sessione. Riduce il rumore, non lo elimina.
  Attribuire per autore vuol dire marcare i commit — altra dimensione.
- `claude_hook_registra_sessione.py` registra `os.getppid()`, che è il wrapper
  dell'hook e muore subito: il registro ha **1 voce con PID morto mentre girano 3
  sessioni**. Molte sessioni non si ritrovano e cadono nel fallback, quindi **il
  fix è spesso inattivo**. È un altro hook: da misurare a parte. → **R9**

**Prove**
- 15 test in `tests/test_hook_reviewer_gate_sessione.py` su repo git veri in
  `tmp_path`, con date di commit esplicite (senza, i commit cadono nello stesso
  secondo e il test misura il proprio setup). **Erano 0 i test sugli hook.**
- Mutazione su copia in scratchpad: 8 mutanti, 8 uccisi. Un nono
  (`not REGISTRO.exists()`) sopravvive ed è ridondanza motivata — `read_text`
  solleva comunque `OSError`, già catturato.
- Suite: 12.658 verdi. Commit `f9383c2`, `92ea72c`, `878af1c`.

**Lezione.** Un mutante non provato è un difetto non trovato: due dei tre difetti
qui sopra erano mutanti che non avevo pensato di provare, e il codice li
conteneva. Il `code-reviewer` ha trovato quello che la mia mutazione non copriva
perché **nessun mio test aveva una sessione con più di un commit**.


---

## 03/09/2026 — Le ultime 3 `pct` di catena, e le 77 righe mai lette

**Verdetto:** chiusa. Leggere l'ultimo file ha però fatto emergere un difetto
**non di catena** → R10.

**Fatto**
- `formatPct` corretta alla forma italiana (`toLocaleString("it-IT")` invece di
  `toFixed`); le 3 `pct` di `sintesi-catena`, `finestra-margini-coperti` e
  `gruppo-tag-section` ora la chiamano. Restano come wrapper: una è passata **per
  riferimento** in `COLS` (`fmt: pct`), due tengono la guardia sul null.
- Letto `catena/fatture/page.tsx` (77 righe): `catena/` da 97% a **100%**.

**Trovato**
- **Il blocco dichiarato non esisteva più.** Era «`formatPct` ha chiamanti fuori
  da catena»: ne ha **zero** — solo la definizione e un re-export. L'ultimo era
  sparito col refactor di giugno (`70136d2`), quindi correggerla non ha toccato
  nessuna schermata. Con un chiamante vivo sarebbe stato un cambio di output.
- `toFixed` non sbagliava solo il separatore: **tronca** dove la forma italiana
  arrotonda (`12.35` → `12.3%` invece di `12,4%`).
- **R10.** `catena/fatture/page.tsx:55` fa `data?.documenti ?? []`, e `workerGet`
  torna `null` su **ogni** fallimento (timeout 8s, non-2xx, rete): il cliente
  legge «Nessun documento trovato» mentre il worker è giù. Non è di catena — lo
  stesso pattern è su ~8 pagine, gemella del PV inclusa
  (`scadenziario/page.tsx:19`). A DB: **3.219 non pagate, 4,4 M€, 1.891 scadute,
  11 sedi**. Il cold-start Railway lo rende ricorrente: `BlockRetry` esiste per
  quello, e lo stesso file lo usa per `overview` e lo perde 15 righe sotto.

**Non fatto, e dichiarato**
- **R10 non corretto**: ~8 pagine, e la scelta (tutte o solo le due dello
  scadenziario) è di Mattia. Fermato e portato a lui. → **R10** in roadmap.

**Prove**
- 5 test nuovi (28 nel file): quello che *fotografava* la divergenza è stato
  **invertito**, come il suo stesso docstring prescriveva.
- Mutazione su copia in scratchpad: **4 mutanti, 4 uccisi** — `toFixed` a monte
  (2 rossi), locale di sistema invece di `it-IT` (2), copia rimessa in un wrapper
  (1), la stessa **nascosta dietro una riga commentata** (1): la classe che era
  sopravvissuta il 3/9 mattina.
- 966 verdi nella regressione frontend/catena, `tsc` pulito. Commit `6dd458c`.

---

## 03/09/2026 — R10: il guasto travestito da «niente da fare»

**Verdetto:** chiuso sulle 7 pagine cliente. Le 2 admin e `impostazioni/`
restano col vecchio schema: **esclusione motivata**.

**Fatto**
- `lib/esito-caricamento.ts`: `esitoLista` distingue «lista vuota» da «non sono
  riuscito a chiedere»; `messaggioListaVuota` / `mostraGuasto` scelgono cosa
  mostrare. Chi carica dichiara quale dei due casi e'.
- Corrette **7 pagine cliente**: scadenziario PV e catena, avvisi desktop e
  mobile, analisi-e-tag, **analisi-fatture**.
- I client accettano `caricamentoFallito`, default `false`: **nessun chiamante
  esistente cambia comportamento**.

**Trovato**
- **Il perimetro era più piccolo di quanto sembrasse.** `?? []` compare ~85
  volte, ma quasi tutte sono `useState`, rami dietro `res.ok` o lookup in
  memoria. La classe pericolosa — caricamento **server** dove `null` diventa
  lista vuota — è **9 pagine**: 7 corrette, 3 escluse. *(Dicevo 8 e ne
  dichiaravo 9: i conti non tornavano, e la pagina mancante era proprio quella
  non dichiarata — `analisi-fatture`, trovata dal reviewer.)*
- Le due pagine avvisi mentivano **due volte** (intestazione e corpo);
  `analisi-e-tag` invitava a «Crea il primo tag» chi ne ha già.
- **Un mio cambio ha introdotto un difetto**, preso rileggendo il diff: la
  chiamata resa condizionale (`token ? … : null`) mostrava «impossibile
  caricare» a chi non ha sessione. Forma originale ripristinata.

**Non fatto, e dichiarato**
- `admin/page.tsx` e `admin/richieste`: le vede solo l'owner. Dichiarato nel
  test (`_PAGINE_CLIENTE`), non taciuto.
- `impostazioni/page.tsx`: una lista sedi vuota è **visibilmente** rotta, non una
  falsa rassicurazione.

**Prove**
- 41 test; **10 mutanti, 10 uccisi.** I primi 6 lasciavano vivi i due del reviewer:
  `? false : false` e `false &&` **contengono** il testo cercato e non compaiono
  mai a schermo. Corretto in due mosse: la scelta estratta in `lib/` (eseguibile
  dall'harness, che non entra nei `.tsx`) e la riga della pagina asserita nella
  **forma esatta**, non per sottostringa.
- `tsc` pulito. Chiavi `documenti`/`sedi`/`articoli` verificate contro il worker.


---

## 03/09/2026 — R5 e R6: due residui rimandati per ipotesi mai misurate

**Verdetto:** chiusi entrambi, **SQL incluso**. Erano in fondo alla roadmap per
due ragioni che la misura ha smontato: nessuno dei due valeva la sessione
dedicata che si temeva.

**R5 — la guardia sui router**
- `dependencies=[Depends(_verify_worker_key)]` su tutti e **12** i router.
- **Non chiudeva una falla**: i **216 endpoint su 216** erano già protetti uno
  per uno. Ripartizione misurata con un audit AST (la prima stesura diceva «il
  solo senza `dependencies` è `svuota-dati`»: **falso**, corretto dal reviewer):
  166 `dependencies=[_verify_worker_key]`, 16 `dependencies=[_verify_admin]` e
  **34 che si affidano alla sola firma** (33 in `admin.py`, 1 in `account.py`) —
  tutti e 34 con `_verify_admin`, cioè la guardia **più** stretta. È prevenzione:
  il 217° non nasce aperto.
- **Il timore era «tocca tutto il traffico».** Misurato: FastAPI esegue prima
  la dependency del router e **poi** quella dell'endpoint — è additiva.
  `_verify_admin` resta più restrittiva dov'era.
- **Prova che non ha rotto niente**: 95 rotte GET senza path-param, con e senza
  `X-Worker-Key`, **0 differenze** di status code fra prima e dopo (snapshot
  confrontati sullo stesso albero).

**R6 — il filtro «Da Classificare»**
- La regola «le righe non classificate restano fuori dal MOL» era scritta a
  mano in **7 punti** (6 `.neq(...)` + 1 nella stringa PostgREST del
  queue-worker), non 9 come diceva la roadmap.
- `CATEGORIA_NON_CLASSIFICATA` **esisteva già** ed era usata negli stessi file
  poche righe più su: le query erano rimaste indietro per inerzia.
- **Nessuna migration**, contro quanto la roadmap dava per certo: la
  sostituzione produce **la stessa identica stringa**. Verificato anche il caso
  non banale — nel filtro PostgREST la virgola separa le condizioni e il punto i
  campi, e `Da Classificare` non contiene né l'una né l'altro.

**Non fatto, e dichiarato**
- I letterali `"Da Classificare"` restanti nel backend Python sono log,
  docstring, default e confronti applicativi: verificato riga per riga che
  **nessuno di essi compare dentro una chiamata di query** (`.neq(`, `.or_(`,
  `.in_(`), cioè nessun filtro di esclusione travestito. Toccarli è un'altra
  dimensione.
- Nessuno: il perimetro SQL, emerso qui, è stato chiuso subito (sotto).

**Prove**
- 27 test in `test_router_dependencies_guardia.py` (uno **esegue** un endpoint
  nuovo senza guardia e verifica che risponda 401 lo stesso) e 9 in
  `test_da_classificare_fonte_unica.py`.
- Mutazione su copia in scratchpad: **6 mutanti, 6 uccisi**. Fra questi
  `APIRouter(dependencies=[])`, che **contiene** la parola cercata e non
  protegge nulla: la lezione del mattino, applicata prima di sbagliarla.


---

## 03/09/2026 — R11: la stessa regola, dall'altra parte del confine

**Verdetto:** chiuso. Emerso chiudendo R6 e chiuso nella stessa sessione: era il
pezzo che rendeva R6 parziale.

**Il problema.** R6 ha dato una fonte unica ai 7 punti Python che escludono le
righe `Da Classificare` dal MOL. Ma la stessa regola di dominio vive **dentro le
RPC PostgreSQL**, e una funzione PL/pgSQL non può importare una costante Python.
Chi cambiasse la stringa da una parte sola otterrebbe due totali diversi nella
stessa pagina — il difetto «fix parziale» già pagato dal progetto.

**Fatto**
- `tests/test_da_classificare_sql_allineato.py`: 14 test che **legano le due
  sponde**. Se la costante Python cambia e l'SQL no (o viceversa), la suite
  diventa rossa.
- **Nessuna migration riscritta**: sono lo storico di ciò che è stato applicato.
  Il test chiede solo che una migration *nuova* usi la stessa stringa.

**Trovato**
- **Il perimetro vero si legge a DB, non nei file.** `pg_proc` sul database di
  produzione dice **7 RPC vive** con la regola (`costi_automatici_mensili`,
  `costi_automatici_mensili_gruppo`, `gruppo_peso_categoria`,
  `gruppo_prezzi_categoria`, `gruppo_spesa_pivot`, `gruppo_spreco_fb_categorie`,
  `gruppo_tag_descrizioni`), tutte con la grafia corretta e lo stesso filtro.
  I file dicono **13 occorrenze su 12 file**, perché contengono anche RPC
  sostituite da versioni successive.
- **Tre cifre diverse per la stessa cosa, tutte sbagliate tranne l'ultima**: il
  reviewer diceva «18 occorrenze su 13 file», io «33 su 20» (contando i
  commenti), la misura in codice vivo dà **13 su 12**, e il DB **7 RPC**. È il
  motivo per cui la regola del progetto è ri-misurare *nel momento in cui si
  scrive il numero*.
- Un primo pattern intercettava anche `categoria <> '📝 NOTE E DICITURE'`, che è
  un'altra esclusione legittima: ristretto ai soli valori che iniziano per
  `Da Cla`, così cattura anche la grafia errata storica.

**Prove**
- 14 test; **3 mutanti, 3 uccisi**: grafia errata `'Da Clasificare'` in una RPC
  (il caso reale: in SQL non dà errore, filtra semplicemente nulla e le righe
  rientrano nel MOL in silenzio), costante Python cambiata senza l'SQL, filtro
  cancellato da una RPC.

---

## 5/09/2026 (sera) — gli ultimi 15 moduli `services/`: la zona rossa del backend chiude

**Perimetro.** I 15 moduli mai auditati. Il prompt diceva 5.147 righe: **ri-misurato,
regge** (`find services -maxdepth 1 -name '*.py' | xargs wc -l`), unico caso del ciclo
in cui una cifra ereditata era esatta. Dopo il lavoro sono **4.821**.

**Due correzioni al prompt, prima di lavorarci.**
- `personale_export_service` era dato «0 test»: ne ha 5 (`tests/test_turni_mensili.py:1060-1195`).
- `documenti_service` era indicato come primo sospetto per la paginazione: **era già
  a posto** (`fetch_all` in 3 punti, con tanto di commento che spiega il perché).
  Il difetto vero stava altrove, e di natura diversa.

### Difetto 1 — i suggerimenti Tag vedevano metà dei prodotti (attivo in produzione)

`_fetch_recent_rows` chiudeva con `.limit(MAX_POOL_ROWS)` (12.000) e `.execute()`.
PostgREST **clampa** quel limit al proprio `max_rows` (1.000) e tronca in silenzio:
un `.limit()` generoso dà la falsa impressione di proteggere.

Misurato a DB il 5/09, righe in finestra 90gg e prodotti distinti visti:

| Sede | Righe | Prodotti visti | Prodotti reali |
|---|---:|---:|---:|
| 5444e918 | 4.209 | 454 | 1.169 |
| cc016821 | 3.973 | 497 | 1.074 |
| 0dca4d1f | 3.608 | 470 | 953 |
| fd7ac484 | 4.343 | 445 | 893 |
| 86300227 | 1.535 | 343 | 440 |

**5 sedi su 11 sopra il cap.** E il pool non è una lista da mostrare: `occorrenze` e
`fornitori` sono conteggi su quelle righe, e `MIN_ROWS_DEFAULT` /
`MIN_FORNITORI_NEW_TAG` si applicano a quei conteggi. Un prodotto la cui seconda
fattura sta oltre la millesima riga risulta comprato da **un solo fornitore**, cioè
sembra una marca, e il suggerimento non nasce mai. Un tag che manca non si nota — a
differenza di uno sbagliato: per questo era invisibile da sempre.

Fix: `fetch_all(query, max_rows=MAX_POOL_ROWS)` più un `.order()` esplicito
(`fetch_all` pagina per OFFSET: senza `ORDER BY` le pagine non sono stabili). La
fonte è unica e serve tutti e 4 i consumatori — nessun consumatore resta indietro.

### Difetto 2 — lo Scadenziario poteva presentarsi pieno e tutto sbagliato

Lo Step 3 di `get_documenti_scadenziario` (lettura di `fatture_documenti`) era
avvolto in un `except Exception` che logga un warning e **prosegue**: `docs_extra`
restava `{}` e ogni documento usciva con `scadenza_eff=None` e `pagata=False`.

La pagina si sarebbe presentata **completa** — le righe vengono dalla RPC dello
Step 2 — ma con tutte le fatture prive di scadenza: **4.408.465,91 €** che
spariscono come scadenze, senza un errore a schermo. Il peggiore dei fallimenti
silenziosi trovati nel ciclo, perché il dato plausibile non fa sospettare nessuno.

Fix: il guasto resta un guasto. Verificate **tutte e 4 le inerenze**: le 3 rotte di
`scadenziario.py` e `gruppo.py` finiscono su `workerGet` → `esitoLista`
(`lib/esito-caricamento.ts`, il fix R10 del 3/09), che distingue il guasto da «zero
scadenze». `/api/scadenziario/notifica` **non è un job batch** (per-utente, nessun
cron): col comportamento vecchio un guasto avrebbe **spento** gli avvisi
interpretandolo come «zero scadenze».

### 280 righe di codice morto rimosse

Blocco M7 «alert soglia costi AI» (85 righe: una feature mai collegata a nulla),
`classifica_via_worker` (62, variante non aggiornata — le mancava la discriminazione
429 quota-vs-ratelimit), `get_documenti_list` con la sua cache a due livelli
irraggiungibile (151 in tutto), `clear_documenti_cache`,
`dismiss_all_inbox_notifications` (nessuna rotta, nessun bottone),
`calcola_costi_gpt4o_mini`. I test di quest'ultima ora chiamano
`calcola_costi_modello`: **misuravano un alias**, non il codice servito.

### Il difetto che ho introdotto io, e che ha trovato il reviewer

Cancellando `_get_documenti_normalized_cached` è rimasto orfano il suo
`@_make_cache(ttl=60)`, che **si è riattaccato alla funzione successiva del file**:
`segna_fattura_pagata`. Una **scrittura** dentro una cache a 60 secondi.

Marcare una fattura pagata, de-marcarla e ri-marcarla entro un minuto: la terza
chiamata è un cache hit — nessuna UPDATE, nessun bump di `cache_version`, nessun
refresh di `pagata_manuale_at`, e l'API risponde `success=True` mentre il frontend
fa aggiornamento ottimistico. I due test esistenti non lo vedevano: usano
`pagata=True` e `pagata=False`, cioè **chiavi di cache diverse**.

**La lezione**: il difetto non è nei due fix dichiarati, è nella rimozione di codice
morto — la parte che sembrava a rischio zero. Un decoratore non è codice della
funzione che lo precede, è codice di quella che lo segue.

**Prove**
- **6 mutanti, 5 uccisi.** Il sopravvissuto è l'`.order()`: il fake restituisce
  sempre le righe in ordine di lista e non può simulare l'instabilità di OFFSET
  senza `ORDER BY` — limite dello strumento, dichiarato, non presidio debole.
- `FakePostgrest` esteso con `.not_` e `.limit()` (che **clampa** a `max_rows`, come
  il server vero) per esercitare la query reale invece di ricalcolare la formula.
- Suite: 12.989 → **12.995** raccolti (+8 pool tag, +2 step3, +1 cache, −5 dei test
  del codice rimosso), **12.951 passed / 44 skipped / 0 failed**.
- 239 rotte montate, `export_openapi.py --check-drift` OK su 196 endpoint: il
  contratto pubblico dell'API non cambia.

**Rilievi lasciati aperti** (misurati, non urgenti): `services/__init__.py:184` — il
`raise` è dentro il `try` e viene ingoiato dall'`except Exception: pass` due righe
dopo (solo diagnostica, e il file è coperto dalla regola #3); campanella notifiche —
`.limit(100)` prima del filtro `dismissed_at` in Python (max attuale 33 su 100);
`ai_cost_service:86` — `return 0` su errore DB fa risultare la quota AI sempre
disponibile; `session_service:184` — un logout globale fallito è indistinguibile da
uno riuscito; `_streamlit_shim` — zero test, e il conftest lo sostituisce con un
MagicMock a superficie aperta, quindi **nessun test esercita mai lo shim reale**.

---

## 5/09/2026 — `(app)/agenda/`: la premessa scaduta due volte, e il buco che c'era davvero

**Verdetto: l'area rossa non era il problema. Il problema l'ha trovato la misura
fatta per aprirla.**

### La premessa, scaduta due volte in direzioni opposte

`AUDIT_COPERTURA.md:188` diceva «**0 turni a DB**: scartata con misura». Il prompt
di sessione l'aveva già corretta il 5/09 sera — «107 turni, campi economici, **muove
soldi che finiscono nel MOL**» — e indicava `agenda/` come prima area proprio per
questo. **Ri-misurato all'apertura, anche la seconda premessa è falsa**, al contrario:

| Misura (5/09/2026) | Valore |
|---|---:|
| `turni_personale` | 107 righe, **1 sola sede**, 3 dipendenti, 1/8–6/9 |
| `costo_orario` valorizzato | **0 / 107** |
| `lordo_mensile` valorizzato | **0 / 107** |
| `importo_extra`, `importo_a_carico` | 0,00 € |
| `dipendenti.costo_orario_default` | NULL su tutti e 4 |

**`agenda/` oggi muove 0 €.** Terza verità sulla stessa area in tre documenti: la
riga di `AUDIT_COPERTURA.md` è stata corretta, non riscritta al ribasso.

### Il buco vero, misurato cercando quello

Il MOL non legge i turni. Legge `margini_mensili.costo_dipendenti +
costo_personale_extra` (`fastapi_worker.py:7469-7479`, `margine_service.py:1124-1126`).
L'unico ponte è `get_costo_personale_da_turni` (`margini.py:966`), **di sola lettura**,
dietro il bottone manuale «Recupera dal tab Personale».

| `margini_mensili` 2026 | Valore |
|---|---:|
| Mesi con `costo_dipendenti > 0` | 50 / 75 |
| **Ultimo mese con costo, su qualsiasi sede** | **luglio** |
| Sedi a 0 su agosto **e** settembre | **6 / 6** (fra cui sedi da 400–473 k€/mese) |

I valori esistenti sono inseriti a mano e si vedono: `60000.00` identico su 3 mesi e
4 sedi, `7319.59` clonato su mag/giu/lug con lo stesso `updated_at`, `20000.00` tondo.
**Nessuno viene dai turni.**

### Non è un bug del briefing — verificato, non dedotto

Ipotesi di partenza: «il presidio tace». **Falsa.** Su `daily_briefing_state` il
28/08 e il 27/08 VILLA GUARDIA riceveva: «👥 Il costo del personale di luglio 2026
non è ancora stato inserito», con CTA «Inserisci costo» → `/margini`. Anche CASATI 14
il 5/09. La logica di `fastapi_worker.py:5540-5566` è corretta (mesi attivi = con
fatturato, fino al mese precedente).

**Il sistema avvisa; il dato non è stato inserito.** È una decisione di Mattia, non
un fix. `_BRIEFING_CODE_VERSION` **non toccato** (nessuna modifica alla logica).

### I due difetti corretti nel ponte

1. **Un «Recupera» a vuoto azzerava il costo del mese.** Con turni privi di
   `costo_orario` l'endpoint torna `costo_dipendenti = 0`, e il dialog faceva
   `setLordo(toStr(0))` → `""`: i campi si svuotavano. Un Salva successivo scriveva
   **0** su un mese che aveva un costo vero (CASATI 14 luglio: **5.074,48 €**),
   togliendolo dal MOL. **È esattamente lo scenario dei 107 turni reali.** Ora un
   recupero che non produce nulla non tocca ciò che c'è.
2. **`costo_assenze_a_carico` calcolato e buttato.** Il worker lo restituisce
   (ferie/malattia a carico datore); il tipo `CalcoloTurni` del dialog non lo
   dichiarava. **Non sommato** — il worker lo tiene isolato di proposito
   (`TestMarginiCostoAssenze`) — ma ora **mostrato**, così l'utente sa che esiste e
   può aggiungerlo a mano.

Logica estratta in `apps/web/src/lib/costo-personale-turni.ts` (il `.tsx` non è
testabile: `helpers_ts.py` esegue solo TS senza React).

### Prove per mutazione — 6 uccisi su 7

Backup preso **prima** del primo mutante, md5 verificato a ogni ripristino (trappola
del 5/09 mattina). Ogni pattern verificato presente prima di mutare.

| # | Mutante | Esito |
|---|---|---|
| 1 | guardia a vuoto rimossa (il difetto originale) | ✅ ucciso |
| 2 | `mostraCostoAssenze` guarda i giorni invece dell'importo | ✅ ucciso |
| 3 | `n_turni <= 0` non è più «nessun turno» | ✅ ucciso |
| 4 | la guardia ignora l'extra | ✅ ucciso |
| 5 | le extra ignorano `costo_orario_extra` | ✅ ucciso |
| 6 | l'ordinario non sottrae le extra (doppio conteggio) | ✅ ucciso |
| 7 | `continue` sui turni senza costo → `co = 0` | ⚠️ **sopravvissuto** |

Il 7° è **codice ridondante, non un test debole**: con `co = 0` i prodotti valgono
zero e il totale non cambia; `n_senza_costo` è già incrementato prima. Isolato con un
mutante mirato (rimozione del solo `n_senza_costo += 1`): **ucciso**. Dichiarato, non
nascosto.

Un primo `sed` di mutazione era fallito silenziosamente (`||` letto come separatore):
il file non era mai stato mutato e il verde non misurava niente. Rifatto in Python
con `assert` sul pattern e md5 a prova.

### Un rilievo aperto, non corretto

**`margini.py:1011` — `min(extra, ore)` è codice morto.** Confronta le ore extra con
`_ore_turno(t)`, che vale `ore_orari + extra`: l'extra è già dentro il totale, non può
eccederlo. Un turno di 8h con `ore_extra = 99` produce 107h e **990 €** di
straordinari, senza tetto. Esposizione oggi **nulla** (0 turni con `ore_extra` su 107),
e correggerlo cambia un importo che entra nel MOL: **è una decisione di Mattia**. Il
comportamento attuale è fissato da un test che lo dichiara.

### Anche `agenda-overview.tsx`

`fmtEuro` e `MESI` locali sostituiti con `@/lib/format` e `@/lib/mesi` (classe di
difetto che il 01/09 valeva 60 punti). **Attenzione misurata**: il `fmtEuro` locale
usava i default di `Intl` (2 decimali), `formatEuro` di lib ha `decimali = 0` — un
`replace` cieco avrebbe arrotondato ogni spesa all'euro. Sostituito con
`formatEuro(v, 2)` ed **equivalenza provata su 10 casi** (0, negativi, arrotondamenti,
milioni): identici.

`layer-switcher.tsx` **non** toccato: il `?? []` sui badge è dichiarato «non critici»,
sono contatori decorativi e non alterano nessun numero di business. Diverso dallo
scadenziario, dove lo stesso pattern nascondeva 4,4 M€.

### Da portare a Mattia

**Il costo del personale è fermo a luglio su 6 sedi su 6.** Senza quel dato il MOL di
agosto e settembre non è confrontabile con i mesi precedenti. Il briefing lo segnala
già: serve l'inserimento, non codice.
