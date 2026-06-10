# ONEFLUX — Assistente AI (chat): funzionamento e guida alle modifiche

Versione: 1.1 | Aggiornamento: 10 Giugno 2026

Questo documento spiega **come funziona la chat con l'assistente AI** (il pannello
flottante in basso a destra nella Home) e **dove mettere le mani** per modificarla.
È gemello di `BRIEFING_HOME.md`: insieme coprono i due volti dell'AI verso il
cliente (briefing = "ti dico io cosa guardare"; chat = "chiedimi quello che vuoi").

> Per la pipeline AI di classificazione/parsing vedi `AI_PIPELINE.md`.
> Per il briefing della Home vedi `BRIEFING_HOME.md`.
> Per lo schema DB vedi `DATABASE_SCHEMA.md`.

---

## 1. Cos'è l'assistente

Un **agente in linguaggio naturale** che risponde a domande sui dati del
ristorante: costi, fornitori, food cost, margini/MOL, scadenze, prezzi,
appuntamenti in agenda. Non è un chatbot che "racconta": è un agente con
**function calling reale** su 7 strumenti che leggono il DB. I numeri che dice
sono **gli stessi della Home** — usa la medesima fonte (`home_kpi`), quindi non
contraddice mai la schermata.

> **Permessi (dal 10/6):** la chat offre al modello **solo gli strumenti delle
> pagine abilitate** all'utente (`pagine_abilitate`). Chi non ha la pagina non
> ne può interrogare i dati nemmeno in chat (vedi §5.1).

**Filosofia (coerente col briefing):**
- **Onesto:** non inventa numeri. Se un dato non c'è, lo dice e propone un'alternativa.
- **Da collega F&B, non da chatbot:** tono diretto, risposte brevi (2-5 righe).
- **Anti-frustrazione:** il ristoratore tipo è poco tecnologico → niente gergo,
  niente "0.0%" grezzi, niente "non risulta nulla" seccanti (vedi §6).

---

## 2. Flusso end-to-end

```
ChatWidget (chat-widget.tsx)            ← pannello flottante, storico in sessionStorage
        │  POST /api/chat  { messages: [...ultimi 16] }
        ▼
route.ts (apps/web/.../api/chat)        ← inoltra al worker con Bearer + X-Worker-Key
        │                                  timeout 35s
        ▼
chat_ai()  [fastapi_worker.py]          ← ENDPOINT
   ├─ _resolve_user_from_token          ← chi è
   ├─ _chat_limite_per_piano            ← quante domande/giorno (per piano)
   ├─ RPC chat_usage_check_and_log      ← rate-limit ATOMICO (conta+logga); fail-closed
   ├─ _build_chat_system_prompt         ← contesto: KPI Home + top categorie/fornitori + agenda di oggi
   ├─ gate tool per pagine_abilitate    ← filtra i tool offerti al modello (§5.1)
   ├─ loop tool-calling (max 3 round)   ← l'LLM chiama gli strumenti che gli servono
   │     └─ _esegui_tool → _chat_*      ← 7 strumenti che leggono il DB
   └─ track_ai_usage                    ← costo €  nel ledger AI (come categorizzazione)
        │
        ▼
ChatResponse { reply, domande_oggi, limite_giorno }
```

**Regola d'oro (come il briefing):** il "cosa dire" sui numeri viene **sempre da
uno strumento che legge il DB**, mai dalla memoria del modello. L'LLM decide
*quale* strumento chiamare e *come* formulare la risposta; i numeri sono del codice.

---

## 3. Modello, limiti, costi

| Cosa | Valore | Dove |
|---|---|---|
| Modello | `gpt-4.1-mini` (override env `CHAT_MODEL`) | `CHAT_MODEL` |
| Temperature | 0.3 | `chat_ai` |
| max_tokens risposta | 900 | `chat_ai` |
| Round tool-calling | max 3 | loop in `chat_ai` |
| Retry su timeout/5xx | 1 | loop interno |
| Timeout OpenAI | 30s (worker) / 35s (route.ts) | client OpenAI + `CHAT_TIMEOUT_MS` |

**Limiti domande/giorno per piano** (`CHAT_LIMITI_PIANO`):

| Piano | Domande/giorno |
|---|---|
| `free` | 0 (chat non disponibile → 403) |
| `base` | 8 |
| `plus` | 15 |
| `pro` | 30 |

> ⚠️ Il modello chat (`gpt-4.1-mini`) è **diverso** da quello del briefing/
> categorizzazione (`gpt-4o-mini`). Scelto per il tool-calling migliore. Budget
> chat Pro ≤ ~3€/mese (vedi memoria `project_chat_ai_decisions`).

**Costo monetario:** ogni risposta accumula i token di **tutti i round** del loop
e li scrive nel ledger via `track_ai_usage(operation_type="chat", ...)` — stesso
sistema della categorizzazione, alimenta l'alert soglia costi mensile.

---

## 4. Rate-limit atomico (anti-abuso, anti-race)

La quota **non** si conta con un SELECT seguito da INSERT (race tra richieste
concorrenti + fail-open). Si usa la RPC **`chat_usage_check_and_log`** che, in un
solo statement, conta le domande di oggi e logga quella nuova solo se sotto soglia:

- ritorna il **numero di domande consumate oggi** se OK;
- ritorna valore "negato" (gestito come `< 0`) se il limite è già raggiunto → `429`.

**Fail-closed:** se la RPC fallisce, l'endpoint **rifiuta** la domanda (`503`), non
la lascia passare. Il log della domanda è già scritto dalla RPC prima della
chiamata OpenAI → niente INSERT a valle.

Il conteggio è per **ristorante** (`ristorante_id`) se presente, altrimenti per
utente. La finestra è il **giorno UTC**.

Il widget mostra le domande rimaste e si sincronizza con la verità del backend a
ogni risposta (`domande_oggi` / `limite_giorno` in `ChatResponse`).

---

## 5. Gli strumenti (function calling)

Tutti definiti in `chat_ai` (lista `tools`) e dispatchati da `_esegui_tool`. Sono
**scoped per ristorante** e filtrano `deleted_at IS NULL` (soft-delete).

| Strumento | Funzione | Per domande tipo | Note |
|---|---|---|---|
| `query_costi` | `_chat_query_costi` | "quanto ho speso in X", "spesa di marzo" | ricerca **tollerante** (singolare/plurale, categoria OR prodotto); fallback "mese corrente vuoto" (§6) |
| `query_scadenze` | `_chat_query_scadenze` | "cosa devo pagare", "scadenze settimana" | stessa fonte della pagina Gestione Fatture |
| `query_margini` | `_chat_query_margini` | "com'è andato il MOL", "andamento margini" | ultimi 6 mesi, stessa fonte di Home/Margini |
| `confronto_prezzi` | `_chat_confronto_prezzi` | "chi mi fa X al prezzo migliore" | cuore di ONEFLUX; ultimi 180gg, miglior prezzo per fornitore |
| `ultimi_acquisti` | `_chat_ultimi_acquisti` | "ultimo acquisto", "ultima fattura di X" | ordine data desc; NON per totali |
| `trend_prezzo` | `_chat_trend_prezzo` | "la mozzarella è aumentata?" | prezzo unitario medio ponderato/mese, ~7 mesi |
| `query_appuntamenti` | `_chat_query_appuntamenti` | "cosa ho oggi", "appuntamenti questa settimana" | **sola lettura** su `diario_eventi`; default oggi→+7gg (10/6) |

**Ricerca tollerante (`query_costi`, `trend_prezzo`, `confronto_prezzi`):** un
termine generico viene cercato **sia su categoria sia su descrizione**, con
fallback singolare/plurale (`_varianti`). Così "birra" trova la categoria "BIRRE".
Tutti e tre i tool di ricerca prodotto sono ora coerenti su questo (fix 9/6).

**Anti-troncamento:** le query con `.limit()` ordinano per `data_documento desc`,
così su clienti con molte righe un eventuale taglio conserva le **più recenti**
(quelle che contano) invece di tagliare a caso. Resta un *full-load* aggregato in
Python (vedi `project_audit_findings_rimandati`): per i clienti attuali va bene,
ma è il punto da spostare lato DB se i volumi crescono.

### 5.1 Gate degli strumenti per permessi pagina (dal 10/6/2026)

Prima di passare la lista `tools` a OpenAI, `chat_ai` la **filtra** in base a
`pagine_abilitate` dell'utente (mappa **`_TOOL_FLAG`** in `chat_ai`). Coerente con
la visibilità della sidebar: **chi non vede una pagina non ne interroga i dati
nemmeno in chat.**

| Strumento | Flag pagina richiesto |
|---|---|
| `query_costi`, `ultimi_acquisti` | `analisi_fatture` |
| `query_scadenze` | `scadenziario` |
| `query_margini` | `margini` |
| `confronto_prezzi`, `trend_prezzo` | `prezzi` |
| `query_appuntamenti` | `agenda` |

- **`pagine_abilitate` = `None`** (admin / nessuna restrizione) → **tutti** i tool
  (stessa semantica di `_normalize_pagine`: None = tutto abilitato).
- Lista presente → resta solo il tool il cui flag è nella lista.

> Il gate è **lato chat** (quali tool offrire al modello). È il fratello del
> **guard di route** lato Next (`requirePagina`, vedi `MIGRAZIONE_NEXTJS.md`):
> uno impedisce di *aprire* la pagina, l'altro di *interrogarne i dati* via chat.

---

## 6. Il system prompt (`_build_chat_system_prompt`)

Costruito **fresco a ogni domanda** con i dati del ristorante. Tre parti:

1. **KPI Home** (`home_kpi`): fatturato, food cost %, costo personale, spese, MOL
   dell'ultimo mese completo → **stessi numeri della schermata**.
2. **Top costi** (ultimi 90gg): top 5 categorie + top 5 fornitori per spesa → la
   chat risponde a "fornitore più caro" / "food cost a colpo d'occhio" **senza
   chiamare uno strumento** (latenza più bassa).
3. **Data e periodo:** oggi + range fatture nel sistema. **Cruciale:** senza, il
   modello usa il suo knowledge cutoff (2024) come anno e cerca sistematicamente
   nell'anno sbagliato → "non risulta nulla" anche quando il dato c'è.
4. **Appuntamenti di oggi** (10/6): se l'utente ha il flag `agenda` e ci sono
   eventi in `diario_eventi` per oggi, vengono iniettati nel prompt → la chat
   risponde a "cosa ho oggi" **senza chiamare lo strumento**. Niente flag agenda =
   sezione assente (e `query_appuntamenti` nemmeno offerto, §5.1).

**Regole-chiave nel prompt (rifinite 9/6/2026 — NON rimuovere senza motivo):**
- **Mese corrente quasi sempre incompleto:** i ristoranti caricano le fatture a
  fine mese / in ritardo. Se "questo mese" è vuoto → **non** dire "non hai speso
  nulla", ma "il mese in corso non è ancora caricato, vuoi l'ultimo disponibile?".
  Supportato lato dato: `query_costi` ritorna `mese_non_ancora_caricato` +
  `ultima_fattura_caricata` + `suggerimento` quando il mese richiesto è il
  corrente/futuro ed è vuoto.
- **Food cost "0.0%"/"n/d" non è un valore reale:** significa quasi sempre che
  mancano i ricavi del mese, non che il cibo costi zero. Va **spiegato** ("non
  calcolabile finché non inserisci i ricavi"), non riportato come dato.
- **Anno corrente di default**, mai un anno passato; "ultimo/recente" non è un
  periodo (cerca il più recente in assoluto).
- **Solo dominio ristorante:** per ricette generiche/notizie/personale risponde
  educatamente che aiuta solo sulla gestione del locale.

> **Perché il prompt è "leggero" (fix 9/6):** prima caricava 3000 righe fattura e
> aggregava anche per prodotto, ad ogni domanda. Ora carica 1500 righe e solo
> categoria+fornitore (il dettaglio prodotto lo dà `query_costi` su richiesta).
> Meno dati dal DB, meno token, **latenza "fornitore più caro" ~4.2s → ~2.9s**.

---

## 7. Coerenza con briefing e Home (importante)

I tre punti di contatto AI col cliente **devono dire la stessa cosa**:

| | Fonte numeri | Modello | Tono |
|---|---|---|---|
| Card "I tuoi conti" (Home) | `home_kpi` | — | — |
| Briefing | `_kpi_periodo` + price_impact | `gpt-4o-mini` | onesto, non sterile |
| **Chat** | **`home_kpi`** + 7 tool | `gpt-4.1-mini` | onesto, da collega F&B |

Chat e briefing **condividono la fonte KPI** (`home_kpi`/`_kpi_periodo`), quindi il
MOL/food cost detti in chat coincidono con quelli del briefing e della card. Se un
giorno cambi la logica KPI, cambiala in un punto e si allineano tutti.

---

## 8. "Dove metto le mani per…" (mappa rapida)

| Voglio… | File / funzione |
|---|---|
| Cambiare modello o parametri (temp, max_tokens, round) | `CHAT_MODEL`, loop in `chat_ai` (fastapi_worker.py) |
| Cambiare i limiti domande/giorno per piano | `CHAT_LIMITI_PIANO` |
| Aggiungere un nuovo strumento | lista `tools` + `_esegui_tool` + nuova `_chat_*` + voce in `_TOOL_FLAG` (§5.1) |
| Cambiare a quale pagina è legato uno strumento | mappa `_TOOL_FLAG` in `chat_ai` |
| Cambiare cosa sa il modello "a colpo d'occhio" | `_build_chat_system_prompt` (parti 1-2) |
| Cambiare le regole di comportamento/tono | testo `sistema` in `_build_chat_system_prompt` |
| Cambiare la ricerca tollerante (singolare/plurale) | `_varianti` in `_chat_query_costi` |
| Cambiare la gestione "mese corrente vuoto" | coda di `_chat_query_costi` (`mese_non_ancora_caricato`) |
| Cambiare il rate-limit | RPC `chat_usage_check_and_log` (DB) + `_chat_limite_per_piano` |
| Cambiare timeout | `OpenAI(timeout=...)` (worker) + `CHAT_TIMEOUT_MS` (route.ts) |
| Cambiare suggerimenti / testo widget | `SUGGERIMENTI`, copy in `chat-widget.tsx` |
| Cambiare il feedback d'attesa | stato `attesa` + effetto in `chat-widget.tsx` |

### Testare la chat in locale

A differenza del briefing, la chat **funziona in locale** se `.env` ha
`OPENAI_API_KEY` (la usa direttamente). Riavvia il worker dopo ogni modifica
Python (uvicorn senza `--reload` tiene il codice vecchio):

```powershell
# riavvia il worker (kill PID su :8000, poi)
$env:PYTHONIOENCODING="utf-8"
.venv\Scripts\python.exe -m uvicorn services.fastapi_worker:app --host 127.0.0.1 --port 8000
```

Per provare domande reali serve un **token di sessione** valido (tabella
`sessioni`) e l'header `X-Worker-Key`. Si chiama `POST /api/chat` con
`{ "messages": [{"role":"user","content":"..."}] }`. Ricorda di **revocare** le
sessioni di test create (`source='chat-eval'`) e che ogni domanda consuma quota
reale del cliente.

---

## 9. Tabelle DB coinvolte

| Tabella | Uso |
|---|---|
| `fatture` | fonte di tutti i tool costi/prezzi/acquisti (filtro `deleted_at IS NULL`) |
| `diario_eventi` | fonte di `query_appuntamenti` + "appuntamenti di oggi" nel prompt (scoped `ristorante_id`) |
| `users` | `piano` (limite chat), **`pagine_abilitate`** (gate tool §5.1), `price_alert_threshold` (non usata dalla chat; si imposta dal **configuratore assistente**, vedi `BRIEFING_HOME.md` §11) |
| `sessioni` | autenticazione token (chat e resto dell'app) |
| `chat_usage_log` | log domande per il rate-limit giornaliero |
| `ai_cost_log` (ledger) | costo € della chat (via `track_ai_usage`) |
| `margini_mensili` + costi auto | fonte MOL/food cost (via `home_kpi`/`_kpi_periodo`) |

---

## 10. File principali

| File | Ruolo |
|---|---|
| `services/fastapi_worker.py` | endpoint `chat_ai`, prompt, 7 tool `_chat_*`, gate `_TOOL_FLAG`, limiti |
| `apps/web/src/app/api/chat/route.ts` | proxy Next.js → worker (auth + timeout) |
| `apps/web/src/app/(app)/dashboard/chat-widget.tsx` | UI pannello, storico, quota, attesa |
| RPC `chat_usage_check_and_log` (DB) | rate-limit atomico |
| `services/ai_cost_service.py` | `track_ai_usage` (ledger costi) |

---

## Changelog rilevante

- **10/6/2026 (Fase D — Agenda nell'assistente)** — 7° tool `query_appuntamenti`
  (sola lettura su `diario_eventi`); **gate degli strumenti per `pagine_abilitate`**
  (`_TOOL_FLAG`, §5.1 — vale anche per i 6 tool preesistenti, prima non filtravano);
  sezione "Appuntamenti di oggi" nel system prompt (solo con flag `agenda`). Lato
  Home/notifiche: nuovo topic `appuntamento_imminente` (vedi `BRIEFING_HOME.md`).
- **9/6/2026** — prompt alleggerito (3000→1500 righe, no aggregazione prodotto);
  fix "questo mese vuoto" (propone l'ultimo mese); food cost 0/n/d spiegato non
  grezzo; `confronto_prezzi` reso tollerante su categoria; `.limit()` ordinati
  per data desc; feedback d'attesa progressivo nel widget. Testato sui 3 clienti
  reali (TIME CAFE, CASATI 14, LAND).
