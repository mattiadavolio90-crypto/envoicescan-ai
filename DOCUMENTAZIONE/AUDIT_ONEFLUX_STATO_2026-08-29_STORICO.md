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
| 2 | nasce un emettitore vivo di `price_alert` | rosso | ✅ ucciso |
| 3 | **controprova**: menzione in un *commento* | **verde** | ✅ nessun falso positivo |

Il 3 non è decorativo: la **prima stesura del test falliva sul docstring che
avevo appena scritto** — cioè sul testo che documenta il difetto. Un match
testuale nudo misura il proprio pattern, non il codice. Ora lo scan salta
commenti e stringhe via `tokenize`.

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
- 7 mutanti in totale, 7 esiti attesi, ognuno verificato montato prima di
  leggerne l'esito

### Non fatto, e dichiarato

- **`scadenziario-client.tsx` resta 2.210 righe di UI non testata** (`wc -l`, 31/8; era 2.244, `lib/scadenziario.ts` 200 → 245). Estratto
  solo `buildCashFlow`. Il resto (rendering, stato, hook, filtri client) richiede
  o altre estrazioni o un runner di componenti — che il punto 9 ha escluso per
  ragione strutturale (`deploy-vercel.yml`).
- **`dependencies=[...]` a livello di `APIRouter`** — invariata dalla sessione
  del 30/8: tocca 238 endpoint, cambia comportamento su tutto il traffico.
