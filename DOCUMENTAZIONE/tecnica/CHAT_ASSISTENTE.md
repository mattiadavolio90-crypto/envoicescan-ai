# ONEFLUX — Assistente AI (chat): funzionamento e guida alle modifiche

Versione: 1.1 | Aggiornamento: 10 Giugno 2026

Questo documento spiega **come funziona la chat con l'assistente AI** (dal
28/9/2026 dentro il riquadro del briefing della Home, prima un pannello
flottante) e **dove mettere le mani** per modificarla.
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
ConversazioneAssistente                 ← nel riquadro del briefing della Home (dal 28/9/2026)
  + AssistenteProvider (layout di (app)) ← una conversazione per vista (sede o catena), in sessionStorage
        │  POST /api/chat  { messages: [...ultimi 16 DELLA VISTA], contesto }
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

**Budget per piano** (dal 23/09/2026 il vincolo primario è il **mese**):

| Piano | Domande/mese (`CHAT_BUDGET_MENSILE_PIANO`) | Domande/giorno (derivate) |
|---|---|---|
| `free` | 0 (chat non disponibile → 403) | 0 |
| `base` | 300 | 30 |
| `plus` | 600 | 60 |
| `pro` | 900 | 90 |

> Il tetto giornaliero **non si scrive a mano**: è `CHAT_QUOTA_GIORNALIERA_PCT`
> (10%) applicata al budget mensile, e `CHAT_LIMITI_PIANO` è costruito da quello.
> Due tabelle di numeri divergono al primo ritocco di una sola.
>
> **Perché il 10%**: il mese deve coprire almeno 10 giorni di uso pieno. Al 20%
> un cliente esaurirebbe il mese in 5 giorni restando fermo per 25 — il problema
> che questo meccanismo esiste per evitare.
>
> Il totale mensile è lo **stesso** di prima (i vecchi 10/20/30 al giorno × 30),
> ma ora è esigibile: fino al 23/09/2026 esisteva solo il tetto giornaliero e il
> mese non aveva alcun limite.
>
> La RPC applica **entrambe** le finestre e dice quale è scattata: `-1` giorno,
> `-2` mese. Il mese è controllato **per primo** perché dura di più — dire «torna
> domani» a chi ha finito il mese lo rimanda a un giorno in cui sarà fermo di
> nuovo. `p_limite_mensile` NULL = comportamento pre-23/09/2026.
>
> ⚠️ **Ordine di deploy OBBLIGATO** per `20260923152816_chat_budget_mensile.sql`:
> la firma della RPC cambia (parametro nuovo), il codice è fail-closed, quindi
> **la migration va applicata PRIMA del push** o la chat si spegne per tutti.
>
> La migration **droppa** la vecchia firma a 4 parametri, e il `DROP` non è
> opzionale. La prima stesura la lasciava viva «così un worker non aggiornato
> continua a funzionare»: **misurato su Postgres vero, fa l'opposto.** Con
> `p_limite_mensile DEFAULT NULL` la firma a 5 è chiamabile anche con 4
> argomenti, quindi le due sono entrambe candidate e Postgres solleva
> `AmbiguousFunction` — il worker vecchio si rompe, e con il fail-closed la chat
> si spegne per tutti. La retrocompatibilità la dà già il `DEFAULT NULL`: una
> chiamata a 4 argomenti risolve sulla firma a 5 e si comporta come prima.
> Stesso `DROP` di `20260619100000_chat_usage_pool.sql`, che è il precedente.

> ⚠️ Il modello chat (`gpt-4.1-mini`) è lo stesso della categorizzazione (dal
> 5/7/2026, dopo A/B test su dati reali), ma **diverso** dal briefing (`gpt-4o-mini`,
> invariato). Scelto per il tool-calling migliore. Budget chat Pro ≤ ~3€/mese
> (vedi memoria `project_chat_ai_decisions`).

**Costo monetario:** ogni risposta accumula i token di **tutti i round** del loop
e li scrive nel ledger via `track_ai_usage(operation_type="chat", ...)` — stesso
sistema della categorizzazione. Il ledger alimenta il pannello admin dei consumi
(l'alert soglia costi mensile e' stato rimosso il 5/09: non ha mai avuto
chiamanti runtime).

---

## 4. Rate-limit atomico (anti-abuso, anti-race)

La quota **non** si conta con un SELECT seguito da INSERT (race tra richieste
concorrenti + fail-open). Si usa la RPC **`chat_usage_check_and_log`** che, in un
solo statement, conta le domande di oggi e logga quella nuova solo se sotto soglia:

- ritorna il **numero di domande consumate oggi** se OK;
- ritorna `-1` se è finito il **tetto giornaliero** → `429`;
- ritorna `-2` se è finito il **budget mensile** → `429` con un messaggio diverso.

> I due casi sono frasi diverse, ed è il motivo per cui il ritorno non è più un
> `-1` secco: «torna domani» a chi ha esaurito il **mese** lo rimanda a un giorno
> in cui sarà fermo di nuovo. Il mese è controllato **per primo** perché dura di
> più. Un chiamante che conosce solo il vecchio contratto legge `-2` come
> "negativo" e blocca comunque: il fail-safe resta dalla parte giusta.

**Fail-closed:** se la RPC fallisce, l'endpoint **rifiuta** la domanda (`503`), non
la lascia passare. Il log della domanda è già scritto dalla RPC prima della
chiamata OpenAI → niente INSERT a valle.

Il conteggio è per **ristorante** (`ristorante_id`) se presente, altrimenti per
utente. La finestra è il **giorno di Europe/Rome**: il contatore si azzera a
mezzanotte per il ristoratore, non per il server.

> Fino al 23/09/2026 la finestra era il giorno **UTC**, cioè l'01:00 di Roma
> d'inverno e le 02:00 d'estate: chi chattava dopo mezzanotte spendeva la quota
> del giorno prima (misurato sul DB live: 1 riga su 95 già addebitata al giorno
> sbagliato). Il fuso vive in **due punti che devono restare allineati** — la RPC
> (`20260923141755_chat_quota_giorno_di_roma.sql`) e il gemello Python
> `_chat_domande_oggi`: se divergono, il contatore mostrato al cliente e quello
> applicato non coincidono più. Presidio: `tests/test_chat_quota_giorno_di_roma.py`.

**Un blocco lascia traccia nei log** (`logger.warning`, dal 23/09/2026). Prima non
la lasciava da nessuna parte: la RPC ritorna `-1` **senza inserire**, e il ramo
`429` non scriveva né su DB né sul logger. Un rifiuto era quindi invisibile, e la
domanda «il tetto ha mai fermato un cliente?» non era rispondibile — non per
assenza di blocchi, ma per assenza dello strumento di misura.

Il widget mostra le domande rimaste e si sincronizza con la verità del backend a
ogni risposta (`domande_oggi` / `limite_giorno` in `ChatResponse`).

---

## 5. Gli strumenti (function calling)

Definiti a livello modulo in `_CHAT_TOOLS_SEDE` e dispatchati da
`_chat_esegui_tool_sede` (fino al 29/9/2026 stavano dentro `chat_ai`). Sono
**scoped per ristorante** e filtrano `deleted_at IS NULL` (soft-delete). In
vista catena si usano anche loro, con una `sede` obbligatoria (§5.3).

| Strumento | Funzione | Per domande tipo | Note |
|---|---|---|---|
| `query_costi` | `_chat_query_costi` | "quanto ho speso in X", "spesa di marzo" | ricerca **tollerante** (singolare/plurale, categoria OR prodotto); fallback "mese corrente vuoto" (§6) |
| `query_scadenze` | `_chat_query_scadenze` | "cosa devo pagare", "scadenze settimana" | stessa fonte della pagina Gestione Fatture; elenco troncato a 30 voci ma il totale le copre tutte (§5.2) |
| `query_margini` | `_chat_query_margini` | "com'è andato il MOL", "andamento margini" | ultimi 6 mesi, stessa fonte di Home/Margini |
| `confronto_prezzi` | `_chat_confronto_prezzi` | "chi mi fa X al prezzo migliore" | cuore di ONEFLUX; ultimi 180gg, miglior prezzo per fornitore |
| `ultimi_acquisti` | `_chat_ultimi_acquisti` | "ultimo acquisto", "ultima fattura di X" | ordine data desc; NON per totali |
| `trend_prezzo` | `_chat_trend_prezzo` | "la mozzarella è aumentata?" | prezzo unitario medio ponderato/mese, ~7 mesi |
| `query_appuntamenti` | `_chat_query_appuntamenti` | "cosa ho oggi", "appuntamenti questa settimana" | **sola lettura** su `diario_eventi`; default oggi→+7gg (10/6) |
| `proponi_incasso` / `proponi_personale` / `proponi_fatturato_mese` / `proponi_spesa` | `proponi` in `services/routers/assistente.py` | "ieri ho fatto 2.340: 1.800 al 10% e 540 senza IVA", "latte 20 euro" | **non scrivono**: preparano una card con Conferma (§5.4); solo con `card_conferma` e pagina `margini` (la spesa: `agenda`), mai in catena |

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
`pagine_abilitate` dell'utente (mappa **`_CHAT_TOOL_FLAG`**, applicata da
`_chat_tools_sede_offerti`). Coerente con
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
- **Sotto-utenti (30/9/2026).** La chat di sede richiede la pagina `home`
  (Home = accesso all'AI), quella di catena la Catena effettiva: il controllo
  in `chat_ai` scatta **prima** della quota. Per loro `pagine_abilitate` è già il
  dict effettivo (pagine del titolare ∩ sue), quindi questo gate e il prompt
  applicano l'intersezione senza codice in più. La quota è **una per account**:
  `user["id"]` è il titolare. Con una sola sede in un account catena il prompt
  nomina la **sua** sede (`_utente_prompt_sede`), non l'account. La
  conversazione in sessionStorage è per persona (`idPersona` in
  `apps/web/src/lib/sotto-utente.ts`). Modello completo:
  `SICUREZZA_GDPR.md` §5bis.

> Il gate vale **su due fronti**: quali tool offrire al modello (`_CHAT_TOOL_FLAG`
> qui) **e** quali dati iniettare nel system prompt (§6). Fino al 25/8/2026 il
> secondo mancava: un utente senza `margini` non poteva chiamare `query_margini`
> ma trovava il MOL già scritto nel prompt — l'invariante dichiarata qui era
> violata da `_build_chat_system_prompt`. È il fratello del **guard di route**
> lato Next (`requirePagina` in `apps/web/src/lib/page-guard.ts`): uno impedisce di
> *aprire* la pagina, l'altro di *interrogarne i dati* via chat.

### 5.2 Troncamento onesto di `query_scadenze` (dal 25/8/2026)

L'elenco restituito si ferma a `_CHAT_SCADENZE_LIMIT` (30) voci, ma
`totale_da_pagare` copre **tutte** le scadenze aperte. Perché il modello non
spacci l'elenco per esaustivo, il tool aggiunge `totale_parziale`, `voci_totali`
e una `nota` esplicita quando tronca.

Ordine di riempimento delle 30 voci, per priorità:

1. aperte **con** scadenza, per data più vicina;
2. aperte **senza** scadenza fino alla quota minima
   `_CHAT_SCADENZE_QUOTA_SENZA_DATA` (10);
3. aperte **senza** scadenza eccedenti la quota, se avanza spazio;
4. pagate (visibili solo con `solo_da_pagare=False`), per ultime.

**Invariante:** nessuna voce pagata compare finché resta una voce aperta non
mostrata. La quota è un **minimo garantito**, non un tetto: i documenti senza
`scadenza_effettiva` sono debito reale (su un cliente valevano il 91% del
totale) e prima del fix sparivano sempre dietro il troncamento. Il campo
`senza_scadenza_non_mostrate` conta quante ne restano davvero fuori.

---

### 5.3 In vista catena, gli strumenti di UNA sede (dal 29/9/2026)

La chat di catena offre, oltre ai quattro strumenti di gruppo, gli strumenti di
sede di `_CHAT_TOOLS_SEDE_IN_CATENA` (tutti tranne `query_coperti`, che legge la
sede dal token) con un argomento **`sede` obbligatorio** (`enum` dei nomi).
Il prompt di catena elenca i punti vendita del gruppo.

- **La sede la sceglie il modello**, quindi è testo influenzabile dal cliente:
  `_chat_risolvi_sede` la accetta solo se è una delle sedi lette da
  `_chat_sedi_catena` (filtro `user_id`, attive, non tecniche; per un
  sotto-utente solo le sue `sedi_operative`). Nome esatto, id di una di quelle
  sedi o un pezzo di nome di almeno 3 lettere che ne identifica una sola.
  Altrimenti l'errore elenca i nomi validi e **nessuna query parte**.
- Alle query va l'**id della riga letta**, mai un valore degli argomenti; la
  `sede` non arriva allo strumento.
- Stessi gate della vista punto vendita (pagine, settore), anche
  all'esecuzione: uno strumento non offerto va al dispatcher di gruppo, che
  risponde «sconosciuto».
- `query_appuntamenti` filtra anche per `user_id` (prima solo per sede).
- Isolamento provato su Postgres vero con due clienti:
  `tests/test_chat_catena_sede_sql.py` (sede di B per nome e per id, più il
  controllo sulle proprie sedi).

### 5.4 Le cifre dettate: proposta, card, Conferma (fase 3, dal 30/9/2026)

Il cliente detta incasso di un giorno, personale o fatturato di un mese, una spesa extra;
l'assistente **propone**, il cliente preme **Conferma**, e solo allora si scrive.

- **Chi le vede.** `ChatRequest.card_conferma` (default `False`) dice che il
  client mostra le card: senza, niente strumenti `proponi_*`, niente regole nel
  prompt (`cifre_dettate` di `_build_chat_system_prompt` e
  `_build_chat_system_prompt_catena`) e gli avvisi di prima. La Home lo manda;
  `/m` no (fase 8). Strumenti mappati su `margini` in `_CHAT_TOOL_FLAG` (`proponi_spesa` su
  `agenda`), fuori
  da `_CHAT_TOOLS_SEDE_IN_CATENA` e rifiutati da `_chat_esegui_tool_sede`: in
  catena il prompt rimanda alla Home del locale.
- **Divisione IVA** (decisione di Mattia, 29/9): si detta IVA inclusa; se il
  cliente dà solo il totale l'assistente chiede quanto al 10% e quanto senza
  IVA, il 22% solo se lo nomina (i negozi: anche il 22%, `_chiedi_divisione`).
  Mai una divisione inventata.
- **La proposta** (`PropostaCifra`) usa le stesse validazioni e letture della
  Conferma (`valida_giorno`, `valida_mese`, tetti, `leggi_fatturato_mese` con la
  sua `fonte`): la card non promette cio' che la Conferma rifiuterebbe. Esce in
  `ChatResponse.proposte` (massimo 3, la stessa cifra due volte = l'ultima,
  nessuna senza `reply`). Importi passati come testo rifiutati («2.340» sarebbe
  2,34).
- **La Conferma**: `POST /api/assistente/registra` (router
  `services/routers/assistente.py`, proxy `app/api/assistente/registra/route.ts`).
  Ricontrolla sede (account, attiva, non tecnica, consentita al sotto-utente) e
  pagina; 409 `valore_cambiato` se il valore non e' piu' quello mostrato
  (`precedente`), `mese_a_totale` / `mese_con_giorni` se il mese e' tenuto in
  altro modo; update condizionato ai valori letti; invalida KPI, briefing e
  campanella.
- **La card** (`components/home/card-cifra.tsx`, logica in `lib/home-chat.ts`:
  `propostaValida`, `testoCard`, `esitoConferma`, `corpoConferma`) vive sulla
  voce della risposta in sessionStorage. Una Conferma ripetuta riceve 409 con
  `attuale` uguale al dettato: il client la legge come registrata.
- **Personale in tre voci** (fase C, 04/10/2026; strumento fase D2): in Margini
  il personale e' Lordo + Ore extra + Chiamata. `proponi_personale` prende
  `importo` (lordo), `ore_extra`, `chiamata` e scrive **solo le voci dettate**
  (`CAMPI_PERSONALE`, `valida_personale`; uno zero vale «non detta», il tetto
  sulla somma). Sulla proposta `costo_dipendenti` / `costo_personale_extra` /
  `costo_personale_chiamata` sono le voci dettate; `restano` (solo card) quelle
  gia' registrate che non si toccano. `precedente` e la condizione dell'update
  stanno sulle sole voci dettate (`leggi_personale(..., campi)`): una voce non
  dettata cambiata nel frattempo non e' un conflitto. Una card della fase C
  rimasta in sessionStorage riceve 409 (mai una scrittura alla cieca).
- **Incassi al 4% e al 5%** (fase D2): `iva4` / `iva5` di `proponi_incasso` e
  `proponi_fatturato_mese`, lordi. Non hanno colonna: come l'import email di
  cassa si scorporano (`netto_da_lordo`) e il netto si somma in
  `altri_ricavi_noiva` (`ALIQUOTE_RIDOTTE`, `_importi_dettati`). La Conferma
  non cambia; `PropostaCifra.iva4` / `iva5` servono alla nota della card.
- **Spesa extra** (fase D1 del piano consulente, 04/10/2026): `proponi_spesa`
  (pagina `agenda`, come il form `ws_spese_crea`) prepara una riga di
  `spese_extra` — categoria scelta dal modello fra `CATEGORIE_SPESA`, tipo
  derivato da lei (`_tipo_da_categoria`), importo al netto se il cliente nomina
  l'IVA (4/5/10/22, `utils/iva.py::netto_da_lordo`), com'e' se non la nomina.
  Anche «altri costi F&B / spese generali del mese» passano da qui, mai dalla
  cella di Margini: la cella si sovrascrive al primo «Recupera dal tab Spese».
  Una spesa si aggiunge (niente `precedente`): `id_proposta` diventa l'id della
  riga, cosi' la Conferma ripetuta non la raddoppia; `doppione` avvisa sulla card
  se nello stesso giorno c'e' gia' una spesa uguale. Nel MOL entra solo con
  «Recupera dal tab Spese» (decisione 2 rivista, fase B): lo dicono il modello e
  il messaggio della card dopo la Conferma (`MESSAGGIO_SPESA_REGISTRATA`). La
  rotta accetta `margini` o `agenda` (`permessi_rotte.py`), poi controlla la
  pagina del tipo (`PAGINA_PER_TIPO`).
- Test: `tests/test_sql_assistente_registra.py`, `tests/test_sql_chat_proposte.py`
  (Postgres vero, due clienti), `tests/test_chat_proposte_prompt.py`,
  `tests/test_home_chat_frontend.py`, `tests/test_assistente_registra_validazioni.py`,
  `tests/test_assistente_spesa_extra.py`, `tests/test_spesa_extra_card_frontend.py`.

### 5.5 Bozze al fornitore: le scrive Score, non l'assistente (dal 3/10/2026)

Dal 30/9 al 3/10 la chat aveva lo strumento `bozza_fornitore`, che mostrava in
una card con Copia la bozza della scheda Score. Mattia l'ha spento il 3/10
(«non mi interessa che l'assistente prepari bozze al fornitore»): strumento,
card e campo della risposta sono stati tolti.

- **Cosa dice il prompt.** Una riga sempre presente, PV e catena, con o senza
  card (`_riga_trattativa`): l'assistente non scrive messaggi o bozze per
  trattare con un fornitore e non si offre di farlo. A chi vede Osservatorio →
  Score Fornitori (pagina `prezzi` senza `tab_off_prezzi_score`, o nessuna
  restrizione) dice che li trova pronti li'; in catena «aprendo quel locale».
- **Dove sta la bozza.** `_bozza_trattativa` in `services/routers/prezzi.py`,
  resa da `prezzi/score-tab.tsx` con il `CopyButton` comune
  (`components/ui/copy-button.tsx`).
- Una conversazione salvata prima del 3/10 con delle bozze: `parseConversazione`
  le scarta (si tengono solo i campi noti).
- Test: `tests/test_chat_bozza_prompt.py`.

## 6. Il system prompt (`_build_chat_system_prompt`)

Costruito **fresco a ogni domanda** con i dati del ristorante. Cinque parti,
**ognuna condizionata al permesso di pagina corrispondente** (dal 25/8/2026, §5.1
— `pagine_abilitate = None`, cioè admin, vede tutto):

1. **KPI Home** (`home_kpi`): fatturato, food cost %, costo personale, spese, MOL
   dell'ultimo mese completo → **stessi numeri della schermata**. Richiede il
   flag `margini`.
2. **Top costi** (ultimi 90gg): top 5 categorie + top 5 fornitori per spesa → la
   chat risponde a "fornitore più caro" / "food cost a colpo d'occhio" **senza
   chiamare uno strumento** (latenza più bassa). Richiede `analisi_fatture`.
3. **Data e periodo:** oggi + range fatture nel sistema. **Cruciale:** senza, il
   modello usa il suo knowledge cutoff (2024) come anno e cerca sistematicamente
   nell'anno sbagliato → "non risulta nulla" anche quando il dato c'è.
   Deliberatamente **non** gated: sono due date di confine, nessun importo, e
   servono a chiunque abbia un tool temporale (anche solo `scadenziario`).
4. **Appuntamenti di oggi** (10/6): se l'utente ha il flag `agenda` e ci sono
   eventi in `diario_eventi` per oggi, vengono iniettati nel prompt → la chat
   risponde a "cosa ho oggi" **senza chiamare lo strumento**. Niente flag agenda =
   sezione assente (e `query_appuntamenti` nemmeno offerto, §5.1).
5. **Avvisi fondamentali:** alert su dati mancanti che falsano i calcoli (fatture
   del mese assenti, ricavi/personale non inseriti, righe `Da Classificare`…).
   Richiede `margini`. L'alert sulle righe non classificate filtra su
   `categoria = CATEGORIA_NON_CLASSIFICATA`, **lo stesso criterio con cui
   `margine_service` le esclude dal MOL** — non su `needs_review`, che comprende
   anche righe già categorizzate marcate per revisione e che nei margini
   rientrano (fix 25/8/2026).

**Onestà sui guasti (25/8/2026):** se una sezione fallisce per un errore tecnico
(Supabase lento, RPC assente), il prompt **lo dichiara** invece di cadere sul
messaggio ottimistico "Nessun dato di costo o margine ancora registrato" — che è
un'affermazione positiva sul cliente che il codice non può verificare, e che il
modello riferirebbe con sicurezza a un cliente con storico reale. Se i KPI ci
sono ma un alert è saltato, il prompt avvisa di non dare i conti per completi:
altrimenti l'assenza di avvisi sembra "tutto a posto".

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

> **Perché il prompt è "leggero" (fix 9/6 → SQL 19/6):** prima caricava 3000 righe
> fattura e aggregava anche per prodotto, ad ogni domanda. Poi 1500 righe + somma
> in Python. **Dal 19/6 le top-list arrivano dalla RPC `chat_top_categoria_fornitore`**
> (aggregazione SQL): zero troncamento (il limit 1500 sottostimava i clienti grandi
> — caso reale: 2070 righe/90gg) e si trasferiscono solo 5+5 righe. Fallback Python
> se la RPC non è ancora deployata.

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
| Cambiare il budget mensile per piano | `CHAT_BUDGET_MENSILE_PIANO` (il giornaliero si ricalcola da solo) |
| Cambiare quanto se ne puo' spendere in un giorno | `CHAT_QUOTA_GIORNALIERA_PCT` |
| Aggiungere un nuovo strumento | `_CHAT_TOOLS_SEDE` + `_chat_esegui_tool_sede` + nuova `_chat_*` + voce in `_CHAT_TOOL_FLAG` (§5.1); se vale anche in catena, `_CHAT_TOOLS_SEDE_IN_CATENA` (§5.3) |
| Cambiare a quale pagina è legato uno strumento | mappa `_CHAT_TOOL_FLAG` |
| Cambiare cosa sa il modello "a colpo d'occhio" | `_build_chat_system_prompt` (parti 1-2) |
| Cambiare le regole di comportamento/tono | testo `sistema` in `_build_chat_system_prompt` |
| Cambiare la ricerca tollerante (singolare/plurale) | `_varianti` in `_chat_query_costi` |
| Cambiare la gestione "mese corrente vuoto" | coda di `_chat_query_costi` (`mese_non_ancora_caricato`) |
| Cambiare il rate-limit | RPC `chat_usage_check_and_log` (DB) + `_chat_limite_per_piano` |
| Cambiare timeout | `OpenAI(timeout=...)` (worker) + `CHAT_TIMEOUT_MS` (route.ts) |
| Cambiare le domande proposte | `SUGGERIMENTI_SEDE` / `SUGGERIMENTI_CATENA` in `lib/home-chat.ts` |
| Cambiare il feedback d'attesa | `testoAttesa` in `lib/home-chat.ts` + effetto in `assistente-provider.tsx` |
| Cambiare quali messaggi si vedono o cosa si manda al backend | `vistaSede`, `vistaCatena`, `vociDellaVista`, `senzaVista`, `codaPerVista` in `lib/home-chat.ts` |
| Cambiare cosa si puo' dettare, tetti, finestre | `services/routers/assistente.py` (`TETTO_*`, `GIORNI_INDIETRO_INCASSO`, `MESI_INDIETRO`, `proponi`) |
| Cambiare cosa dice la card o come legge l'esito | `testoCard`, `esitoConferma` in `lib/home-chat.ts`; resa in `components/home/card-cifra.tsx` |
| Cambiare il testo della bozza al fornitore | `_bozza_trattativa` in `services/routers/prezzi.py` (scheda Score); cosa dice la chat se gliela chiedono: `_riga_trattativa` |

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
| `services/fastapi_worker.py` | endpoint `chat_ai`, prompt, tool `_chat_*`, gate `_CHAT_TOOL_FLAG`, strumenti di sede in catena (§5.3), limiti |
| `apps/web/src/app/api/chat/route.ts` | proxy Next.js → worker (auth + timeout) |
| `apps/web/src/components/home/assistente-provider.tsx` | stato della conversazione (layout di `(app)`), invio, attesa |
| `apps/web/src/components/home/conversazione-assistente.tsx` | la conversazione nel riquadro del briefing: vista, quota, domande proposte |
| `apps/web/src/components/home/pannello-conversazione.tsx` | il disegno, comune alla Home e al Demo Tour |
| `apps/web/src/lib/home-chat.ts` | logica pura: messaggi della vista aperta, coda da inviare, contatore, card delle cifre dettate |
| `services/routers/assistente.py` | cifre dettate: proposta (`proponi`) e Conferma (`POST /api/assistente/registra`) (§5.4) |
| `apps/web/src/components/home/card-cifra.tsx` | la card con Conferma / Annulla |
| RPC `chat_usage_check_and_log` (DB) | rate-limit atomico |
| `services/ai_cost_service.py` | `track_ai_usage` (ledger costi) |

---

## Changelog rilevante

- **3/10/2026 (piano assistente consulente, fase A; non ancora pushato al
  momento della nota)** — bozze al fornitore spente (§5.5): via lo strumento
  `bozza_fornitore`, la card con Copia e il campo `bozze` della risposta; il
  prompt rimanda a Osservatorio → Score Fornitori. Demo Tour allineato.

- **30/9/2026 (fase 3, step 4; non ancora pushato al momento della nota)** —
  bozza al fornitore nella conversazione della Home (§5.5): strumento
  `bozza_fornitore` (pagina `prezzi`), `ChatResponse.bozze`, card con Copia;
  `CopyButton` estratto da Score in `components/ui/`.

- **30/9/2026 (fase 3, step 1-3; non ancora pushati al momento della nota)** —
  cifre dettate con Conferma (§5.4): endpoint `POST /api/assistente/registra`,
  strumenti `proponi_*` accesi da `card_conferma`, card nella conversazione della
  Home. La data «di oggi» dei due prompt ora e' quella di Roma (`_oggi_rome`):
  fra mezzanotte e le 2 il server in UTC diceva il giorno prima.

- **29/9/2026 (interfaccia dell'assistente, step 6)** — in vista catena la chat
  usa anche gli strumenti di una sede, con `sede` obbligatoria e verificata fra
  le sedi dell'account (§5.3). Lista e dispatcher degli strumenti di sede
  spostati da `chat_ai` a livello modulo (`_CHAT_TOOLS_SEDE`,
  `_chat_esegui_tool_sede`, `_CHAT_TOOL_FLAG`). `query_appuntamenti` filtra
  anche per `user_id`. Il prompt di catena elenca i punti vendita e non dice
  più «apri quel punto vendita» quando l'elenco c'è.
- **29/9/2026 (interfaccia dell'assistente, step 5)** — nella vista punto
  vendita di chi vede più sedi il prompt nomina la **sede aperta**
  (`_chat_nome_sede`), non l'account, e un blocco «Solo questo locale» dice di
  non rispondere su altri punti vendita ma di rimandare alla vista catena. Un
  sotto-utente con una sola sede non riceve il blocco. Mono-sede: prompt byte
  per byte invariato. Una guardia 409 sulla sede a schermo è stata scritta e
  tolta prima del push: `/auth/me` e `chat_ai` leggono la sede attiva da cache
  per processo diverse, e dopo un cambio di sede divergono per qualche secondo
  (falso blocco nel passaggio catena → punto vendita). Domande proposte per
  settore (`suggerimentiPer`: i negozi non leggono food cost, pesce né
  scontrino).
- **29/9/2026 (una conversazione per vista)** — Mattia: la conversazione unica
  che continuava cambiando locale, sotto un briefing diverso, confondeva. Ora
  ogni locale e la catena hanno la loro: sotto il briefing si vedono solo i
  messaggi di quella vista (`vociDellaVista`), cioè esattamente quelli che il
  modello riceve; le altre restano salvate e si ritrovano tornandoci. «Nuova
  conversazione» ricomincia solo quella della vista (`senzaVista`). Via le righe
  «Ora sei in…». Sui 5xx la chat mostra un messaggio suo, mai il testo tecnico
  del server (`messaggioRisposta`).
- **28/9/2026 (interfaccia dell'assistente, step 4)** — via il pulsante flottante
  «Chiedi a ONEFLUX»: la conversazione vive nel riquadro del briefing delle due
  Home, con domande proposte, casella e contatore. Una conversazione sola per
  scheda (stato in `AssistenteProvider`, montato nel layout di `(app)`), con la
  riga «Ora sei in…» al cambio di sede o di vista. Al backend vanno solo i
  messaggi della vista in cui si scrive (prima catena e PV condividevano la
  chiave `oneflux:chat-messages` e lo storico). La chiave di sessionStorage è
  per utente. `/m` non cambia (fase 8).
- **19/6/2026 (hardening + SQL)** — limiti domande/giorno **base 10 / plus 20 / pro 30**
  (`CHAT_LIMITI_PIANO`). Loop tool-calling **unificato** su `_chat_loop_openai` (sede
  + catena, niente più duplicazione) con **chiamata finale `tool_choice="none"`** a
  round esauriti (basta "Non sono riuscito a elaborare la risposta") e **log
  strutturato** (round + tool chiamati + reply_vuota). System prompt: riga
  **anti-prompt-injection** (output tool = dato grezzo, non istruzioni). `ChatRequest`:
  **cap 24k caratteri totali** oltre al limite per-messaggio. Top categorie/fornitori
  del prompt da **RPC `chat_top_categoria_fornitore`** (no troncamento). `query_costi`:
  flag **`totale_parziale`** quando si raggiunge il tetto righe (`_CHAT_COSTI_LIMIT=8000`).
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
