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

### Prova per mutazione — 6 mutanti, 6 uccisi

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

Il 5 è il più importante: è il modo esatto in cui il segnale di questa rete
potrebbe essere aggirato, ed è coperto.

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
- `python -m pytest tests/` → **11.511 passed, 43 skipped**, nessuna regressione
- Baseline radar ricontrollata a inizio sessione: `notification_inbox` 65 record
  — `operativa` 58 (ultima 28/8), `upload` 7 (ultima **1/6/2026**, blocco morto
  confermato), **`radar` 0**. Nessuna ritaratura da rivedere.
