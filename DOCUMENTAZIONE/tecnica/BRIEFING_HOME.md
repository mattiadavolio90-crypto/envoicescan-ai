# ONEFLUX — Briefing Home AI: funzionamento e guida alle modifiche

Versione: 1.2 | Aggiornamento: 10 Giugno 2026 (topic `appuntamento_imminente` — Agenda nel briefing/notifiche)

Questo documento spiega **come funziona il briefing della Home** (il saluto + "Da
fare oggi" + apertura positiva) e **dove mettere le mani** per modificarlo senza
ri-analizzare tutto da zero. È la fonte di verità per: cosa appare, perché, in
che ordine, con che tono, e quali file toccare per cambiarlo.

> Per la pipeline AI generale (classificazione/parsing) vedi `AI_PIPELINE.md`.
> Per lo schema DB vedi `DATABASE_SCHEMA.md`.

---

## 1. Cos'è il briefing

Il briefing è il blocco in cima alla Home (`/dashboard`). Ha tre parti:

1. **Saluto** — "Buongiorno/Buon pomeriggio, {nome}" (nome dal configuratore, mai
   la ragione sociale).
2. **Narrativa** — un discorsetto colloquiale che riassume la giornata. Apre con
   una **buona notizia** (se c'è) e poi elenca le cose da sistemare.
3. **Card "Da fare oggi"** — le notifiche azionabili come bottoni cliccabili
   (max 5). La buona notizia **non** è una card.

**Filosofia (decisa da Mattia):** non è un report, è il "buongiorno". Deve essere
**onesto** (mai dire cose false → il cliente si fida) e **non sterile** (quando le
cose vanno bene, lo dice). Vedi memoria `project_chat_ai_decisions` e
`feedback_oneflux_filosofia_design`.

---

## 2. Flusso end-to-end

```
notification_inbox (DB)            ← notifiche persistite (upload falliti, ecc.)
        +
segnali LIVE calcolati ogni volta  ← buona notizia, alert prezzi, ricavi auto KO,
        │                            dati mensili mancanti, incasso ieri mancante
        ▼
_briefing_raccogli_notifiche()     [fastapi_worker.py] — unisce tutto in una lista
        │
        ▼
_build_snapshot()                  [daily_briefing_service.py] — FILTRA+ORDINA+taglia
   ├─ estrae 'buona_notizia' a parte (apertura, non card)
   ├─ _is_actionable()             ← scarta il non-azionabile/inutile
   ├─ _TOPIC_PRIORITY              ← ordina per TEMA, poi gravità
   ├─ _bullet_for()                ← testo di ogni card
   └─ _compose_narrative()         ← discorsetto template (apertura + to-do)
        │
        ▼
_narrate_with_ai()                 [daily_briefing_service.py] — l'AI RISCRIVE
        │                            il discorsetto in tono umano (NON i numeri)
        ▼
daily_briefing_state (DB)          ← snapshot del giorno (cache)
```

**Regola d'oro:** l'AI **non calcola e non decide nulla**. Riceve frasi già
pronte coi numeri giusti e le riscrive più calde. Tutto il "cosa dire" è
deterministico, fatto dal codice prima dell'AI. I nomi propri (prodotti) vengono
anonimizzati prima di andare a OpenAI e ripristinati dopo.

---

## 3. Cache-first: i tre fast-path

L'endpoint è `GET /api/home/briefing` → funzione **`home_briefing()`** in
`fastapi_worker.py`. Il briefing è un dato **giornaliero** e la generazione
completa è pesante (alert prezzi + OpenAI), quindi non si calcola a ogni load:

1. **Fast-path 1 — cache di oggi.** Se esiste lo snapshot di oggi in
   `daily_briefing_state`, lo serve subito (~0.5s). Caso normale.
2. **Fast-path 2 — "mai bloccante".** Manca lo snapshot di oggi: risponde
   **subito** con l'ultimo snapshot disponibile (max di ieri, marcato `_stale`) e
   lancia la rigenerazione completa in **BackgroundTask**
   (`_briefing_rigenera_async`). Il briefing completo di oggi sarà pronto al load
   successivo dal fast-path 1.
3. **Template istantaneo.** Cliente nuovo / nessuno snapshot mai generato:
   template deterministico leggero dalle sole notifiche inbox (niente AI né alert
   prezzi). La versione completa arriva dal background.

> ⚠️ **Conseguenza pratica:** dopo una modifica al codice del briefing, lo
> snapshot di oggi in cache è ancora quello vecchio. Per vedere subito il nuovo
> testo bisogna **invalidare** la cache (vedi §7).

### Invalidazione della cache (`invalidate_today_briefing`)

Lo snapshot di oggi diventa stantio quando cambiano i dati che racconta. Va
invalidato **agli eventi**, non rigenerato a ogni render. Punti che invalidano:

| Evento | File |
|---|---|
| Upload fatture | `invoice_service.py` (~1863) |
| Inserimento ricavi/costi manuale | `routers/margini.py` (~296, ~362) |
| Ricavi batch (email automatica / import XLS) | `routers/ricavi.py` — `upsert_ricavi_batch` |

---

## 4. Cosa può comparire — i topic

I topic sono in **`_TOPIC_PRIORITY`** (`daily_briefing_service.py`). Ordine =
priorità (più basso = appare prima). **Prima il TEMA, poi la gravità nel tema.**

| Priorità | topic_key | Quando appare | Card? |
|---|---|---|---|
| 0 | `buona_notizia` | C'è un fatto positivo fresco (vedi §5) | ❌ apertura narrativa |
| 10 | `upload_failed` | Fattura automatica non caricata | ✅ |
| 15 | `upload_ricavi_failed` | Ricavi auto fermi da X giorni (solo clienti mappati) | ✅ |
| 20 | `price_alert` | Rincaro rilevante (vedi §6) | ✅ |
| 30 | `uncategorized_rows` | Righe senza categoria | ✅ |
| 40 | `fatturato_mancante` | Manca il fatturato del mese scorso | ✅ |
| 45 | `incasso_mancante` | Manca l'incasso di ieri | ✅ |
| 50 | `costo_personale_mancante` | Manca il costo del lavoro del mese | ✅ |
| 60 | `scadenza_superata` | Fatture scadute | ✅ |
| 61 | `scadenza_imminente` | Fatture in scadenza ≤7gg | ✅ |
| 70 | `appuntamento_imminente` | Appuntamenti in agenda **per oggi** (importanza medio/bassa, severity `info`) | ✅ |

I segnali **LIVE** (calcolati a ogni generazione, non persistiti) sono prodotti
in `_briefing_raccogli_notifiche` e nei suoi helper:
- `buona_notizia` → `_briefing_buona_notizia` (fastapi_worker.py)
- `price_alert` → `services/price_impact_service.py` (budget 4s, timeout-safe)
- `upload_ricavi_failed` → check `ricavi_ragione_sociale_map` + `ricavi_giornalieri`
- `fatturato_mancante` / `costo_personale_mancante` / `incasso_mancante` →
  `_briefing_dati_mensili_mancanti`
- `appuntamento_imminente` → `_briefing_appuntamenti_oggi` (dal 10/6)

> **`appuntamento_imminente` è l'eccezione che PERSISTE** (non è solo live):
> `_briefing_appuntamenti_oggi` fa `upsert_inbox_notifications` in
> `notification_inbox` (source_type `agenda`, bucket **giornaliero**, expires
> **1 giorno**). Motivo: la pagina Avvisi (`get_notifiche`) legge **solo dal DB**,
> e il requisito è che l'appuntamento compaia sia nel briefing sia lì. Bucket
> giornaliero = una notifica per ristorante al giorno, auto-pulente. Rispetta il
> flag pagina **`agenda`** (niente flag → niente promemoria) e il toggle del
> configuratore (`appuntamento_imminente` in `topics_disabled`).

> I topic live **rimpiazzano** eventuali versioni legacy in inbox (scritte dalla
> vecchia pagina Streamlit, mai aggiornate): `_briefing_raccogli_notifiche` le
> rimuove prima di aggiungere quelle live, altrimenti una legacy stantia
> vincerebbe (`_build_snapshot` tiene la prima occorrenza per topic_key).

### Perché un topic NON appare

Ogni topic è una **cosa-da-fare che si spegne quando la fai**: `_is_actionable`
(daily_briefing_service.py) lo scarta se il dato è a posto (count 0, dato
inserito, ecc.). È **voluto**: il briefing è una to-do list. Se è "triste"
(monotematico) è perché tutto il resto è a posto — non è un bug.

---

## 5. Apertura positiva (`buona_notizia`)

Prodotta da **`_briefing_buona_notizia(user_id, ristorante_id, sb)`** in
`fastapi_worker.py`. Sceglie **UNA** apertura, in quest'ordine (la prima che si
applica vince), e ritorna `None` se nessuna → briefing to-do puro.

| Priorità | tipo payload | Condizione | Esempio |
|---|---|---|---|
| 1 | `mol_mese` | MOL del mese chiuso **> 0 E in crescita** vs mese prima | "🔥 Maggio chiuso con € 280.924, +172,1% rispetto ad aprile" |
| 2 | `perdita_in_calo` | MOL **< 0 ma migliore** del mese prima | "💪 Maggio in miglioramento: perdita scesa a € 1.037, sei sulla strada giusta" |
| 3 | `incasso_ieri` | Esiste un incasso **di IERI** (e solo di ieri) | "💰 Ieri sono entrati € 11.543 di incasso" |

**Decisioni di design (Mattia, 9/6/2026) — NON violare senza motivo:**
- **Mai confronti fuorvianti nell'eco quotidiana.** L'incasso è eco grezza del
  dato di ieri, senza "+/- vs ieri/settimana" (sagre/chiusure/meteo falsano). Il
  confronto c'è solo nel MOL, su orizzonte pulito (mese chiuso vs mese chiuso).
- **Incasso solo se di IERI.** Oltre il giorno prima non è una notizia fresca →
  silenzio. (`buona-notizia-incasso-{ieri}`).
- **MOL solo se in crescita** (non il mese in corso, incompleto per via del costo
  dipendenti che arriva a fine mese).
- **Perdita in calo è incoraggiante** ma onesta: non finge profitto.
- **Niente apertura forzata:** se non c'è un fatto fresco e solido, to-do puro.
  Meglio sobri che fuorvianti.

Il MOL è ricalcolato con la **stessa fonte/logica di `home_kpi`** (`_kpi_periodo`
+ margini_mensili + costi auto da fatture), così la card "I tuoi conti" e
l'apertura del briefing **non si contraddicono mai** (stesso numero, stessa %).

**Rendering testo:** `_buona_notizia_bullet` (per l'AI) e `_buona_notizia_frase`
(template), entrambi in `daily_briefing_service.py`. Distinguono per
`payload['tipo']`.

---

## 6. Alert prezzi (price_impact_service.py)

Motore separato, chiamato in `_briefing_raccogli_notifiche` con budget 4s
(timeout-safe: se sfora, il briefing esce comunque senza alert). Logica:
"non conta la % di aumento da sola, conta l'**IMPATTO** = peso × aumento, e solo
sui prodotti/tag che contano davvero".

Funzione principale: **`calcola_alert_prezzi_impatto(user_id, ristorante_id, sb)`**.
Finestra storica `_FINESTRA_GIORNI = 90`. Max alert mostrati `_MAX_ALERT = 3`.

### Criteri di rilevanza (rivisti 9/6/2026)

**Soglia % = quella del cliente** (`users.price_alert_threshold`, impostata in
pagina Prezzi, default `_SOGLIA_PERC_DEFAULT = 5.0`). Letta da
`_leggi_soglia_perc_cliente`. È il "di quanto deve aumentare un prezzo perché mi
interessi" deciso da lui → niente soglie magiche nostre.

**PRODOTTI** — un prodotto entra solo se TUTTE:
1. variazione % ≥ soglia cliente
2. impatto €/mese > 0
3. è nella **fascia Pareto 80%** della spesa food (`_prodotti_pareto`,
   `_PARETO_QUOTA = 0.80`)

→ Il **Pareto** è il cuore: tiene eleggibili solo i prodotti che cumulano l'80%
della spesa, **adattandosi alla frammentazione** del cliente (concentrato = pochi
pilastri; frammentato = di più). Così i marginali (es. limoni) restano fuori
**anche se rincarano tanto in %**. Niente % di peso fissa (che taglierebbe male a
seconda di quanti prodotti ha il cliente).

**TAG** — un tag del cliente entra se:
1. variazione % ≥ soglia cliente
2. impatto €/mese > 0
**Nessun filtro di peso** (no Pareto). Decisione Mattia: "se ha creato il tag, ci
tiene → deve sempre poter rientrare". I tag sono il suo focus dichiarato.

> Pre-filtro candidati: `calcola_alert(df, soglia_minima=_SOGLIA_PERC_CANDIDATO)`
> con `_SOGLIA_PERC_CANDIDATO = 3.0` (genera candidati, poi si applica la soglia
> cliente). Deve restare ≤ soglia cliente minima sensata.

---

## 7. Narrativa AI vs template

- **Template** (`_compose_narrative`): deterministico, sempre disponibile.
  Apertura buona notizia + "prima il bene, poi la rogna" + to-do + chiusura.
- **AI** (`_narrate_with_ai`): riscrive il template in tono umano. Modello
  `gpt-4o-mini`. System prompt: `_NARRATION_SYSTEM_PROMPT`.

**Regole nel system prompt (NON rimuovere senza motivo):**
- Non inventare/modificare numeri, importi, %, date, nomi.
- Se la prima voce è una buona notizia (emoji 🔥 💪 💰), apre col positivo.
- I problemi (rincari, scadenze, dati mancanti) → tono neutro/allerta, **mai
  aggettivi entusiasti** ("un bel +X%" è vietato). Entusiasmo solo sul positivo.

> In **locale** senza `OPENAI_API_KEY` la narrativa è sempre il **template** (l'AI
> fallisce e fa fallback). In **cloud** la chiave c'è → vedi la versione AI. Per
> testare il *contenuto/struttura* basta il template; per testare il *tono AI*
> serve l'ambiente cloud.

---

## 8. "Dove metto le mani per…" (mappa rapida)

| Voglio… | File / funzione |
|---|---|
| Cambiare l'ordine in cui appaiono i topic | `_TOPIC_PRIORITY` (daily_briefing_service.py) |
| Aggiungere un nuovo topic | builder live in `_briefing_raccogli_notifiche` + caso in `_is_actionable`, `_bullet_for`, `_narrative_phrase_for`, `_TOPIC_ACTION` |
| Cambiare l'importanza del promemoria appuntamenti | numero priorità di `appuntamento_imminente` in `_TOPIC_PRIORITY` (70 = medio/bassa) |
| Cambiare quando scatta il promemoria appuntamenti | `_briefing_appuntamenti_oggi` (fastapi_worker.py) — oggi è "solo oggi" |
| Cambiare quando un topic appare | `_is_actionable` (daily_briefing_service.py) |
| Cambiare il testo di una card | `_bullet_for` (daily_briefing_service.py) |
| Cambiare il discorsetto template | `_compose_narrative` / `_narrative_phrase_for` |
| Cambiare il tono/regole dell'AI | `_NARRATION_SYSTEM_PROMPT` |
| Cambiare la logica apertura positiva | `_briefing_buona_notizia` (fastapi_worker.py) |
| Cambiare i testi apertura positiva | `_buona_notizia_bullet` / `_buona_notizia_frase` |
| Cambiare soglia/criteri alert prezzi | `price_impact_service.py` (`_alert_prodotti`, `_alert_tag`, `_prodotti_pareto`, costanti `_PARETO_QUOTA`, `_SOGLIA_PERC_DEFAULT`, `_FINESTRA_GIORNI`, `_MAX_ALERT`) |
| Cambiare max card mostrate | `_MAX_CARD` (daily_briefing_service.py) |
| Aggiungere un punto che invalida la cache | chiamare `invalidate_today_briefing(user_id, ristorante_id, sb)` all'evento |

### Far ripartire il briefing in locale dopo una modifica

Il worker (uvicorn senza `--reload`) tiene il codice vecchio in memoria. Dopo
aver editato un file Python del briefing:

```powershell
# 1. riavvia il worker (kill PID su :8000, poi)
.venv\Scripts\python.exe -m uvicorn services.fastapi_worker:app --host 127.0.0.1 --port 8000

# 2. rigenera lo snapshot di oggi per un cliente (script ad hoc):
#    invalidate_today_briefing(...) -> _briefing_raccogli_notifiche(...) ->
#    generate_and_save_briefing(...)
# 3. ricarica localhost:3000/dashboard
```

> ⚠️ Il Next locale punta al **DB cloud condiviso**: rigenerare uno snapshot in
> locale lo scrive sul DB reale dei clienti. Va bene per i 3 account di test, ma
> esserne consapevoli.

---

## 9. Tabelle DB coinvolte

| Tabella | Ruolo |
|---|---|
| `daily_briefing_state` | Snapshot giornaliero (cache). Chiave: user_id+ristorante_id+generated_for_date |
| `notification_inbox` | Notifiche persistite (upload, ecc.) lette dal briefing |
| `assistant_preferences` | `nome_referente` (saluto) + `topics_disabled` (configuratore) |
| `users.price_alert_threshold` | Soglia % alert prezzi scelta dal cliente |
| `margini_mensili` | Fonte MOL/fatturato per apertura positiva e KPI |
| `ricavi_giornalieri` | Incasso di ieri (apertura positiva) + check ricavi auto |

---

## 10. File principali

| File | Contenuto |
|---|---|
| `services/fastapi_worker.py` | Endpoint `home_briefing`, raccolta notifiche, `_briefing_buona_notizia`, `_briefing_dati_mensili_mancanti`, fast-path/cache |
| `services/daily_briefing_service.py` | `_build_snapshot`, filtri/ordinamento, bullet/narrativa, AI, CRUD snapshot, `invalidate_today_briefing` |
| `services/price_impact_service.py` | Motore alert prezzi per impatto (prodotti + tag, Pareto, soglia cliente) |
| `services/notification_inbox_service.py` | CRUD notification_inbox, dedupe, query |
| `services/notification_service.py` | Builder notifiche (scadenze, dati mensili, ecc.) |
| `apps/web/src/app/(app)/dashboard/page.tsx` | Render Home (BriefingBlock, KpiBlock, ecc.) |
| `apps/web/src/lib/home.ts` | `fetchBriefing`/`fetchKpi`/... (proxy verso worker) |

---

## 11. Configuratore assistente ("Configura assistente")

Dialog in Home (`config-assistente.tsx`) → `GET/POST /api/home/config` →
`assistant_preferences` (per-ristorante) + `users.price_alert_threshold`
(per-utente). Definizione avvisi: **`_CONFIG_TOPICS`** (fastapi_worker.py), una
4-tupla `(key, label, bloccato, descrizione)`.

Gestisce: **nome referente** (saluto), **Chat AI on/off** (`chat_ai_enabled`),
**toggle avvisi**, **soglia alert prezzi**.

### Coerenza toggle ↔ topic del briefing (fix 9/6/2026)

Un interruttore del configuratore può governare **più topic dello stesso tema**.
Mappa: **`_TOPIC_SPENTO_ESTENDE`** + helper **`espandi_topic_spenti`**
(daily_briefing_service.py), usato sia dal briefing (`_build_snapshot`) sia dal
filtro notifiche (`_filtra_notifiche_topic_spenti`).

| Toggle UI | key salvata | Topic effettivamente spenti |
|---|---|---|
| "Scadenze" | `scadenza_superata` | `scadenza_superata` **+ `scadenza_imminente`** |
| "Promemoria appuntamenti" | `appuntamento_imminente` | `appuntamento_imminente` (10/6 — singolo tema) |

> Prima del fix: spegnere "Scadenze" lasciava comparire le scadenze **imminenti**
> (key non mappata) → incoerenza. Ora il tema si spegne tutto insieme. Per
> aggiungere altri "interruttori che coprono più topic" basta estendere
> `_TOPIC_SPENTO_ESTENDE`. Bloccati (`upload_failed`, `upload_ricavi_failed`)
> restano sempre attivi.

### Soglia alert prezzi: unico punto di impostazione (9/6/2026)

La soglia % che fa **scattare** l'avviso "Alert prezzi" si imposta **solo qui**
(sotto il toggle "Alert prezzi"). Salva su `users.price_alert_threshold` e
**invalida il briefing** di oggi (cambia quali rincari diventano avvisi).

In **pagina Prezzi** (`variazioni-tab.tsx`) lo stesso numero resta come **filtro
di sola visualizzazione**: muoverlo cambia cosa vedi in quella pagina, **non
salva** e non tocca gli avvisi. `GET /api/prezzi/soglia-alert` serve solo a
leggere il valore di partenza. Il `POST` worker omonimo è **deprecato** (nessun
frontend lo chiama, tenuto per compat OpenAPI).

---

## Changelog rilevante

- **10/6/2026 (Fase D — Agenda nel briefing/notifiche)** — nuovo topic
  `appuntamento_imminente` (priorità **70** = importanza medio/bassa, severity
  `info`), generato da `_briefing_appuntamenti_oggi` **solo per gli appuntamenti
  di oggi**. Unico topic del briefing che **persiste** in `notification_inbox`
  (source_type `agenda`, bucket giornaliero, expires 1g) così compare anche nella
  pagina Avvisi. Toggle "Promemoria appuntamenti" in `_CONFIG_TOPICS`; rispetta il
  flag pagina `agenda`. Lato chat: tool `query_appuntamenti` (vedi
  `CHAT_ASSISTENTE.md`).
- **9/6/2026** — §11 configuratore: fix coerenza toggle Scadenze
  (`_TOPIC_SPENTO_ESTENDE`) + soglia alert prezzi come unico punto di impostazione.
