# L8 — Matrice cache / snapshot / invalidatore

**Misurato il 15/09/2026**, commit di partenza `da96dac`. Perimetro ri-misurato in
sessione, **non ereditato** dal prompt: dove le cifre del prompt divergono, vale
questa pagina e la differenza è spiegata.

> **La domanda della lente.** Le altre hanno chiesto «il numero è giusto?».
> Questa chiede **«il numero è giusto ma il cliente sta vedendo quello di
> ieri?»** — un valore corretto, servito vecchio da una cache che nessuno ha
> invalidato, o da uno snapshot scritto da un codice che nel frattempo è
> cambiato.

---

## Il perimetro, ri-misurato

| Cosa | Prompt (15/09) | Misurato | Nota sulla differenza |
|---|---|---|---|
| File backend che nominano cache/TTL | 10 | **21** file, **595** righe | il prompt contava un grep più stretto; la cifra grezza è rumore (variabili locali chiamate `cache`, memoria AI, pool di client) |
| Cache **dichiarate** (AST, non grep) | — | **82** in 20 file | inventario `scratchpad/inv_cache.py`: assegnazioni a nome `*cache*` + decoratori |
| Cache che **servono dati al cliente** | — | **14** strutture + **12** funzioni `@_make_cache` | è questa la riga su cui vive la lente, non le 595 |
| Punti di invalidazione | 56 | **82 righe**, riconducibili a **11 invalidatori con nome** | `clear_fatture_cache`, `clear_tags_cache`, `clear_fornitori_cache`, `clear_fatturato_centri_cache`, `clear_ai_deadline`, `invalidate_today_briefing`, `_invalidate_fatture_rows_cache`, `_invalidate_home_kpi_cache`, `_invalidate_sede_attiva_cache`, `_invalidate_assist_pref_cache`, `_invalidate_prezzi_rows_cache` (+4 wrapper espliciti nei router, che non sono invalidatori nuovi) |
| File frontend con direttive | 132 file / 165 occorrenze | **132 / 165** ✔ | confermato: 158 `no-store`, 4 `revalidate`, 3 `force-dynamic`, 0 `unstable_cache` |
| Tabelle di stato/snapshot vive | 3 | **3** ✔ | `cache_version` (3), `daily_briefing_state` (53), `gruppo_segnali_state` (40) — tutte scritte il 15/09 |
| Funzioni trigger di bump a DB | 3 | **3** ✔ | invariato |
| `_BRIEFING_CODE_VERSION` | 24 | **24** ✔ | `services/daily_briefing_service.py:135` |

---

## La matrice: scrittura × cache × invalidatore

Legenda: **✔** invalidatore esplicito · **TTL** la scadenza *è* la politica ·
**∅** cella vuota.

### Cache in-process del worker (per-processo, `WORKER_WEB_CONCURRENCY`)

| Cache | TTL | Cosa serve | Chi la invalida | Esito |
|---|---|---|---|---|
| `_FATTURE_ROWS_CACHE` | 15 s | righe fatture di Analisi | `_invalidate_fatture_rows_cache` (upload, categoria, cestino, admin) | ✔ |
| `_RISTORANTE_QUOTE_META` | — | quota/meta sede | stesso invalidatore | ✔ |
| `_PREZZI_ROWS_CACHE` | 15 s | righe di Prezzi | invalidata **a cascata** dallo stesso punto: le due pagine leggono le stesse righe | ✔ |
| `_HOME_KPI_CACHE` | 120 s | card «I tuoi conti» | `_invalidate_home_kpi_cache` (margini, ricavi, personale, upload) | ✔ |
| `_SEDE_ATTIVA_CACHE` | — | sede attiva per token | `_invalidate_sede_attiva_cache` (switch sede) | ✔ |
| `_ASSIST_PREF_CACHE` | 30 s | preferenze assistente | `_invalidate_assist_pref_cache` | ✔ |
| `_LIVE_SEGNALI_CACHE` | — | segnali live per-sede | invalidata su salvataggio preferenze | ✔ |
| `_SESSIONE_CACHE` | 30 s | sessione autenticata | `.clear()` su logout/revoca | ✔ |
| `_DASHBOARD_STATS_CACHE` | 60 s | stats dashboard | — | TTL |
| `_TRIAL_INFO_CACHE` | 30 s | info trial | — | TTL |
| `_ADMIN_CACHE` | 45 s | overview/consumi/badge admin | — | TTL (solo owner) |
| `_cache_utenti` / `_cache_sedi` | TTL | settore della sede | `settore_service` invalida entrambe | ✔ |
| `_memoria_cache` (AI) | 3600 s | memoria classificazione | **cross-processo** via `cache_version.memoria_classificazione`, polling 30 s | ✔ |
| `_SUPABASE_CLIENT_CACHE`, `_CLIENT_CACHE` | — | pool di client | non servono dati: fuori perimetro | n/a |

### Funzioni `@_make_cache` (cache **vera** dal commit `0bed331`)

Prima erano un no-op: per anni **dichiaravano un TTL senza cachare**. Reso reale,
quindi ognuna ha avuto bisogno di un invalidatore vero.

| Funzione | TTL | Invalidatore | Esito |
|---|---|---|---|
| `_carica_fatture_da_supabase`, `_fetch_numero_documento_map_cached`, `get_fatture_stats`, `get_descrizioni_distinte`, `get_fatture_cestino` | 60–300 s | `clear_fatture_cache()` | ✔ |
| `calcola_costi_automatici_per_anno`, `carica_costi_per_categoria` | 300 s | `clear_fatture_cache()` via `sys.modules` (import circolare) | ✔ |
| `get_custom_tags`, `get_custom_tag_prodotti` | 300 s | invalidate su salvataggio tag | ✔ |
| `get_price_alert_threshold` | 120 s | invalidate su cambio soglia | ✔ |
| `_get_fornitori_pagamenti_config_cached` | 120 s | invalidate + `cache_version.fornitori_pagamenti_config` | ✔ |

### Snapshot persistiti a DB — **qui stava la cella vuota**

| Tabella | Chiave | Versione della logica | Invalidatore | Esito |
|---|---|---|---|---|
| `daily_briefing_state` | user+sede+giorno Roma | **`code_version` nello snapshot**, confrontata da `snapshot_is_stale()` + TTL 30' | `invalidate_today_briefing` (14 call site) | ✔ |
| `gruppo_segnali_state` | account+giorno Roma | **∅ nessuna** → corretto, vedi sotto | solo `delete` per-account al salvataggio config | **∅ → ✔** |
| `cache_version` | chiave logica | n/a (è lei il meccanismo) | 3 funzioni di bump | ✔ |

### Frontend

129 file su 132 sono `no-store`: la politica è **non cachare**, che è la scelta
sicura. Le 3 `force-dynamic` sono pagine `/m`. L'unico `revalidate` vero è
`revalidateSec` in `apps/web/src/lib/fatture.ts:125` e ha **zero chiamanti**:
ogni chiamata cade nel ramo `no-store`. Nessuna cella vuota — dichiarato e non
rimosso (rimuoverlo sarebbe riprogettare, fuori perimetro).

---

## Il difetto trovato, e corretto

### La cache dei segnali catena sopravviveva ai deploy

`gruppo_segnali_state` ha **la stessa forma** di `daily_briefing_state` (snapshot
JSONB, chiave per giorno di Roma) ma **non** registrava la versione della logica
che l'aveva prodotto.

**Misurato sul DB live:** 40 righe su 40, dal 28/06 al 15/09, su 3 account —
**zero** con la chiave `code_version`.

**Conseguenza:** per un account multi-sede che aveva già letto i segnali di oggi,
un deploy che cambiava `_calcola_segnali` o le sue soglie **non si vedeva fino a
mezzanotte di Roma**. L'unico svuotamento esistente è per-account, al salvataggio
della config assistente; e `force=true` esiste nella firma ma ha **zero chiamanti
di produzione** (`card-segnali.tsx:35`, `mobile-catena.tsx:61`,
`api/gruppo/segnali/route.ts:19` chiamano tutti senza forzare).

**Platea:** misurata a DB, **3 account** hanno ≥2 sedi attive non tecniche (5, 2 e
2 sedi) — il gate a 400 di `_resolve_gruppo` esclude gli altri. Sono esattamente i
3 che hanno righe nella tabella: la platea è piccola, ma è interamente esposta.

**Il fix** (`services/routers/gruppo.py`): `_SEGNALI_CODE_VERSION = 1`, scritta
nello snapshot e confrontata in lettura da `_snapshot_versione_corrente()`. Stesso
patto di `_BRIEFING_CODE_VERSION`, e va bumpata per la stessa ragione.

**Presidiati entrambi i lettori**, non uno solo:
1. l'endpoint `gruppo_segnali` — ricalcola invece di servire;
2. `_conta_segnali_cache` (`gruppo.py:529`) → il **briefing di catena**, che
   riceve `(n_segnali, severity_max)`. Su versione diversa ritorna `None`
   («non determinabile»), **non `0`**: il gate `tutto_ok` non deve accendersi su
   un conteggio che non vale più — stesso contratto già presidiato da
   `test_catena_errore_non_diventa_tutto_ok.py` per la cache assente.

Presidiare solo il primo avrebbe prodotto il difetto gemello: la pagina
aggiornata e il briefing fermo ai segnali di ieri.

**Le 40 righe già in produzione** si rigenerano da sole al primo deploy: uno
snapshot senza `code_version` non è corrente per costruzione. Nessuna migration,
nessuna pulizia manuale.

### Presidio e prova per mutazione

`tests/test_segnali_catena_snapshot_versionato.py` — **17 test**, che *eseguono*
il codice vero con un finto client Supabase: nessun assert sul sorgente, nessun
controllo sul decoratore.

**6 mutanti, 6 uccisi**, tutti verificati come *applicati davvero* (conteggio
occorrenze == 1 e hash del file cambiato prima di lanciare):

| # | Mutante | Esito |
|---|---|---|
| M1 | il controllo in lettura non c'è più (il difetto originale) | 4 rossi |
| M2 | la scrittura non registra la versione | 1 rosso |
| M3 | `_conta_segnali_cache` senza controllo (**il fix parziale**) | 3 rossi |
| M4 | snapshot senza `code_version` accettato come corrente | 13 rossi |
| M5 | `code_version` illeggibile accettato | 2 rossi |
| M6 | `_conta` ritorna `0` invece di `None` (`tutto_ok` si accende) | 3 rossi |

Backup preso **prima** del primo mutante; file ripristinato identico a fine giro
(hash confrontato).

---

## Verifica avversaria

Un agente refutatore in **sola lettura** ha ricevuto il rilievo con l'incarico di
smontarlo. Verdetto: **regge**, ma ha corretto **due mie affermazioni**, entrambe
verificate poi in autonomia:

1. la funzione che alimenta il briefing **non** si chiama `_segnali_sintesi`
   (non esiste): è **`_conta_segnali_cache`**;
2. lo snapshot stantio **non** propaga i *testi* dei segnali al briefing, solo
   **conteggio e severity massima** — quindi un deploy che cambia solo la
   formulazione non contamina il briefing. Il rilievo difendibile è l'asimmetria
   sull'invalidazione da deploy, **non** la durata della cache in sé.

Ridimensionato anche l'impatto: **account multi-sede soltanto**, e la staleness è
«fino alla mezzanotte di Roma successiva» (da pochi minuti a quasi un giorno
secondo l'ora del deploy), non «24 ore».

---

## Ordine di deploy

Misurato sulla coda del 15/09/2026 (**ri-misurare prima di pushare**: la
composizione scade in minuti):

- coda: **30 commit**, tutti dell'owner;
- **1 solo** tocca `apps/web/**` (`74c2d76`) → fa partire **Vercel**; gli altri 29
  solo **Railway**, che non ha filtro di path (anche i soli `.md` ridispiegano il
  worker);
- quel commit è **frontend-puro** (`analisi-fatture/page.tsx`, `margini/page.tsx`,
  `lib/oggi-roma.ts`): non cambia nessuna rotta del worker, quindi **in questa
  coda non c'è disallineamento** — il frontend nuovo non chiama niente che il
  worker non esponga già.

**Rotte orfane: nessuna.** `scripts/export_openapi.py --check-drift` → *198
endpoint, nessun drift*, quindi l'inventario delle rotte esposte è affidabile.
I 7 path che il primo rilevatore segnalava come «citati dal frontend e non
esposti» erano **tutti falsi positivi**: 5 per la query string attaccata al path
(`${qs}`), e 2 perché il confronto saltava **il livello proxy** — le route API di
Next traducono (es. `POST /api/notifiche/dismiss` con l'id nel *body* →
`/api/notifiche/{id}/dismiss` del worker, `apps/web/src/app/api/notifiche/dismiss/route.ts`).
Lezione di metodo: confrontare due strati non adiacenti produce allarmi, non
difetti.

**Edge Function** (che col push **non si deployano affatto**): scrivono solo su
tabelle di coda — `fatture_queue`, `ricavi_email_queue` — che **nessuna cache
serve al cliente**. È il worker a processarle e a invalidare a valle. Nessuna
cella vuota da quel lato.

---

## Dichiarato e NON corretto

- **Tre `@st.cache_data` dichiarano `ttl=120` e non cachano nulla**:
  `db_service.py:804`, `db_service.py:1140`, `margine_service.py:633` usano
  `import streamlit as _st_*`, che sotto il worker è lo **shim passthrough**
  (`services/_streamlit_shim.py:41`). Non è un difetto di freschezza — il cliente
  vede il dato vivo — ma è **un TTL che mente**, l'opposto del difetto cercato.
  Toglierli o renderli veri è una scelta di politica, fuori perimetro.
- **`clear_fatture_cache` invalida le due cache di `margine_service` solo se il
  modulo è già in `sys.modules`** (`db_service.py:1733-1739`). In pratica lo è
  sempre — chi ha popolato quelle cache lo ha importato — ma la dipendenza è
  implicita e nessun test la copre.
- **Il ramo `pages.foodcost`** nello stesso invalidatore è **codice morto**:
  `pages/` contiene solo un `__pycache__` non tracciato da git (Streamlit rimosso
  il 17/07/2026).
- **`revalidateSec`** (`lib/fatture.ts:125`) ha zero chiamanti.
- **`force=true`** su `gruppo_segnali` ha zero chiamanti di produzione.
- Il **cron delle 06:30 UTC al cambio d'ora del 25/10/2026** resta il residuo
  dichiarato da L6: è un monitor, non una cache. Non riaperto qui.

---

## Si riapre se…

- si aggiunge una **tabella di snapshot** (oggi sono 3): deve nascere con la
  versione della logica dentro, o eredita esattamente questo difetto;
- si tocca `_calcola_segnali` o le sue soglie → **bumpare `_SEGNALI_CODE_VERSION`**
  (come per `_BRIEFING_CODE_VERSION`: è la trappola che questa lente auditava);
- si aggiunge una cache che serve dati al cliente: va in questa matrice con il suo
  invalidatore, o la cella resta vuota;
- si rende vera una delle tre `@st.cache_data` passthrough: allora servono
  invalidatori che oggi non esistono perché non servivano.
