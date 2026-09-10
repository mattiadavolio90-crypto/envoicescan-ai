# Implementazione retail — documento operativo

Stato al **10/09/2026**. Piano di progetto (contesto, decisioni, difetti misurati):
`~/.claude/plans/mi-piacerebbe-che-l-app-curious-milner.md`.
Copia locale: `docs/piani/PIANO_RETAIL.md` (in `.gitignore`).

> Questo documento si aggiorna **durante** il lavoro, non alla fine: le caselle si
> spuntano quando il gate di fase è passato, non quando il codice è scritto.

---

## Il vincolo, in una riga

I clienti ristorazione non devono vedere **nessun cambiamento, nemmeno un'etichetta**.
Ogni differenza retail è una deviazione che scatta su `tipo_attivita = 'retail'`; il
percorso comune resta letteralmente quello di oggi.

**Regola operativa**: nessuna scrittura sul DB di produzione, in nessuna fase. Solo
letture. Il 10/9 uno script di snapshot ha creato 308 voci in `prodotti_utente` su 4
clienti reali (cancellate, DB riportato allo stato esatto): è la ragione dei presidi
in `scripts/retail_baseline.py`.

**Dove si lavora**: branch `retail` nel worktree `/home/vscode/ONEFLUX-retail`.
Mai su `main`: il push serale spedisce tutto `main`, e un retail a metà significherebbe
codice che legge `tipo_attivita` prima che la migration esista.

---

## Fase 0 — Snapshot di riferimento e messa in sicurezza

- [x] Worktree `/home/vscode/ONEFLUX-retail` su branch `retail`
- [x] Tag `pre-retail` su `origin/main` (`8acc543`); `main` allineato, 0 commit in coda
- [x] Backup 5 tabelle in `/home/vscode/oneflux-backup/20260910_105630` (3,3 MB),
      verificato nel contenuto (non solo nei conteggi): 1.393 correzioni manuali
      presenti, riga campione identica al DB
- [x] Cifre del piano ri-misurate sul DB vivo
- [x] `scripts/retail_baseline.py` di sola lettura, **due presidi indipendenti**,
      provato per mutazione: delta 0 su `prodotti_utente` e `prodotti_master`
- [x] **Misura dell'impatto del difetto d'ordine: ZERO** (10/9/2026) — vedi sotto
- [x] **Snapshot riproducibile: 5 check verdi consecutivi** (10/9/2026)
- [ ] Verbale + commit di fase ← unico punto rimasto

### Impatto del difetto d'ordine: misurato, è ZERO

Misurato il 10/9/2026 in sola lettura, su **tutte le sedi con dati**. Ogni sede
classificata due volte con lo stesso campione di righe reali: (A) da sola con cache
azzerata, (B) dopo tutte le altre sedi — cioè il caso peggiore del worker in produzione.

**Risultato: 0 divergenze su 3.075 righe di campione, in 10 sedi su 10.**

| Sede | Righe campione | Divergenze |
|---|---|---|
| CASATI 14 | 400 | 0 |
| Costi comuni di gruppo | 316 | 0 |
| LAND DEI SAPORI SRL | 400 | 0 |
| OFFSIDE SPORTS PUB | 400 | 0 |
| OVERTIME | 284 | 0 |
| SUSHILAND MARIANO COMENSE | 400 | 0 |
| SUSHILAND SAN GIULIANO M. | 400 | 0 |
| SUSHILAND VILLA GUARDIA | 400 | 0 |
| TIME CAFE | 400 | 0 |
| Ambiente Test Admin (×2, omonime) | 75 + 75 | 0 |

Due note di copertura, entrambe verificate e non problematiche:
- «Ambiente Test Admin» sono **due sedi omonime** di test: il filtro per nome le misura
  entrambe, 0 divergenze in entrambe;
- **IL BARETTINO è saltata perché ha 0 righe fattura** — è la 12ª sede senza dati, non un
  errore di misura.

**Conseguenza**: l'ordine di elaborazione **non** cambia la classificazione dei clienti in
produzione. Il difetto d'ordine osservato il 10/9 su Villa Guardia (11 divergenze su 400)
**non si riproduce** ora che `_azzera_cache_memoria()` gira prima di ogni sede: quelle 11
divergenze erano un artefatto dello snapshot senza azzeramento, non un difetto vivo del
prodotto.

Il rischio va quindi **derubricato**: resta vero che la cache è di processo e condivisa,
ma sui dati reali non produce effetti. Nessuna correzione da fare prima del retail.

### Snapshot riproducibile: VERIFICATO (10/9/2026)

Il presidio **funziona ed è affidabile**. Provato nel suo uso reale — `capture` in un
processo, `check` in processi nuovi e separati:

```
capture  -> 3475 righe
check #1 -> Diff a zero: 56 righe di costi e 3475 categorie invariate.
check #2 -> Diff a zero: ...
check #3 -> Diff a zero: ...
check #4 -> Diff a zero: ...
check #5 -> Diff a zero: ...
```

**Cinque verifiche consecutive verdi**, tutte in processi separati. È esattamente il modo
in cui il gate lo userà: si cattura prima di una fase, si verifica dopo.

**Determinismo provato per costruzione**, non assunto:
- tre processi identici sulla stessa sede: **0 divergenze**;
- due catture complete nello stesso processo: **0 divergenze**;
- N sedi precedenti (N = 0, 1, 2, 3, 5, 8) prima della sede target: **0 divergenze** —
  l'ordine di elaborazione non influisce;
- lettura paginata di `prodotti_utente`, 20 esecuzioni: **3.067 righe sempre**, con e
  senza `ORDER BY`.

**Sulla baseline vecchia di stamattina** (ore 10:58, 22 divergenze su San Giuliano più 2 su
Villa Guardia): tutte le divergenze andavano in **una sola direzione** — la baseline diceva
`Da Classificare`, il ricontrollo risolveva. Solo 4 delle 24 venivano dalla memoria locale;
le altre 20 dal dizionario, che non dipende da alcuno stato. La causa esatta di quella
cattura **non è stata isolata**: sei ipotesi (polling `cache_version`, `_brand_union_cache`,
proxy di sola lettura, `_loaded_user_ids`, paginazione senza `ORDER BY`, baseline obsoleta)
sono state **tutte testate e tutte scartate** con misure.

Resta un fatto non spiegato di quella singola cattura. **Non blocca il lavoro**: il presidio
è stato ri-catturato ed è verde in modo ripetibile, che è la proprietà che serve al gate.
La baseline in uso è quella nuova.

**Regola operativa che ne consegue**: la baseline si ri-cattura **all'inizio di ogni fase**
e il `check` si esegue **in un processo nuovo**, mai riusando un processo che ha già
catturato. Un `check` verde una volta sola non è una prova: se ne fanno **due**.

### Difetto d'ordine: derubricato

La misura dell'impatto (sopra) e le prove di determinismo qui convergono: **l'ordine di
elaborazione non cambia la classificazione**. Le 11 divergenze osservate su Villa Guardia
il 10/9 erano un artefatto della cattura senza `_azzera_cache_memoria()`, non un difetto
vivo. **Nessuna correzione da fare prima del retail.**

---

## Fase 1 — Isolamento · **bloccante per tutte le altre** · Fable, ultrathink, ~3 giorni

Nessuna fase successiva parte prima che questa abbia passato il gate.

### 1.1 Migration e perno

- [ ] `supabase/migrations/AAAAMMGGHHMMSS_add_tipo_attivita.sql`:
      `ALTER TABLE ristoranti ADD COLUMN tipo_attivita TEXT NOT NULL DEFAULT 'ristorazione'`
      + `CHECK (tipo_attivita IN ('ristorazione','retail'))`
- [ ] **Ereditarietà della sede tecnica**: l'INSERT dentro `assegna_fattura_a_sede_tecnica`
      (`supabase/schema_snapshot.sql:1614-1621`) elenca 6 colonne e non include
      `tipo_attivita` → su un account retail la sede tecnica nascerebbe `'ristorazione'`.
      Copiare il valore dalla stessa sede reale da cui già copia la P.IVA
- [ ] `_SEDE_SELECT` (`services/routers/admin.py:2930`), `NuovaSedeBody` /
      `ModificaSedeBody` (`:2933-2953`, pattern come `piano`), `admin_crea_sede` (`:2966`,
      insert a `:2991`), `admin_modifica_sede`
- [ ] **Vincolo di omogeneità** in `admin_crea_sede`, con `.eq("sede_tecnica", False)`:
      la sede tecnica è esclusa dal vincolo (coerente coi 15+ punti che già la escludono)
- [ ] `UserPublic` (`services/fastapi_worker.py:1176`) e `SessionUser`
      (`apps/web/src/lib/auth.ts:19`), campo additivo col default
- [ ] Frontend admin: form sede in `cliente-dettaglio-client.tsx`, tipo `Sede` in
      `apps/web/src/lib/admin.ts:3`

### 1.2 `services/settore_service.py` (nuovo)

Modulo separato: `ai_service.py` è già importato da mezzo mondo, e la funzione serve anche
a router che non fanno AI.

- [ ] `settore_utente(user_id)` e `settore_sede(ristorante_id)`
- [ ] Cache modulo-level con `threading.Lock` + TTL **300s** (pattern di `_memoria_cache`,
      `ai_service.py:290-291`; TTL corto: il settore cambia solo per mano dell'admin)
- [ ] Query: `user_id = ? and attivo = true and sede_tecnica = false limit 1`
- [ ] **Utente senza sedi → `'ristorazione'`** (caso reale: `auth_service.py:517-520`
      crea account senza sedi se manca la P.IVA). Fail-safe nella direzione giusta
- [ ] Risolto **una volta per documento**, fuori dal loop righe
- [ ] **Mai** negli header del client Supabase: è un singleton condiviso, i suoi header
      sono stato globale e hanno già rotto la produzione. Il dato viaggia come argomento

### 1.3 Filtro d'uscita nella classificazione

`categorizza_con_memoria` (`services/ai_service.py:4905-5182`) **non chiama mai l'AI**:
finisce sul dizionario. Il canale per mandare una riga all'AI esiste già ed è restituire
`Da Classificare` con `is_fallback=True` — i chiamanti lo interpretano come "passala
all'AI e marca `needs_review`" (`services/invoice_service.py:1157-1170`).

- [ ] Gate dentro la closure `_ret` (`:4952-4980`): **tutti i 12 return passano di lì**,
      nessun early-return la salta. Se retail e la categoria è in `CATEGORIE_FOOD_BEVERAGE`
      → `Da Classificare` + `is_fallback=True`, provenienza `"nessuna"`
- [ ] **Non filtrare** i livelli generici, corretti anche per un negozio: L0 fornitore
      utility → UTENZE, L4 dicitura → NOTE (gate `prezzo == 0`), L6 unità di misura,
      guardrail. Il gate guarda **solo** l'appartenenza alle food
- [ ] Seconda guardia sull'auto-save locale (`:5124`): riceve `categoria_keyword`, non il
      ritorno di `_ret` — il filtro da solo non lo blocca

### 1.4 Post-AI: quattro punti che riporterebbero in food

- [ ] **`:5412` — bloccante**: `if cat not in TUTTE_LE_CATEGORIE` sostituisce la categoria
      con `decisione_deterministica(desc)`. Senza questo, il prompt retail (Fase 2) **non
      produce nulla**, qualunque cosa risponda GPT, e il sintomo sarebbe indistinguibile
      da "il prompt non funziona". Whitelist di validazione funzione del settore —
      **mai** aggiungere `ARTICOLO DI VENDITA` a `TUTTE_LE_CATEGORIE`
- [ ] `:5629` safety net (`decisione_deterministica` sui `Da Classificare`): saltare se retail
- [ ] `:5676` override post-AI (`applica_regole_categoria_forti`): saltare se retail
- [ ] `worker/queue_processor.py:487` `_categoria_deterministica_runtime`: scavalca la
      proposta AI quando il dizionario è certo. Saltare se retail

### 1.5 Memoria globale — 2 scritture, 3 letture

- [ ] Scrittura `aggiorna_streak_classificazione` (`:3240`): guardia **nel chiamante**
      (`worker/queue_processor.py:543`, che ha `user_id` in scope). Firma invariata
- [ ] Scrittura `salva_correzione_in_memoria_globale` (`:4673`), via `routers/admin.py:1657`
- [ ] Lettura L3 dentro `categorizza_con_memoria` (`:5068`, `:5080`) — già coperta da `_ret`
- [ ] Lettura `suggerisci_categoria_da_memoria` (`:3839`) — **funzione diversa**, legge in
      proprio: guardia separata
- [ ] Lettura `_hint_da_memoria_globale` (`:3546`) — inietta un hint nel **prompt GPT**
      ("CARNE" su una riga di ferramenta): sfugge a qualunque filtro d'uscita

### 1.6 Propagazione storica — il difetto più grave, esiste già oggi

`_propaga_global_override_a_fatture_storiche` (`services/ai_service.py:4581-4590`): la
query su `fatture` filtra per `deleted_at` e per token della descrizione, **senza alcun
filtro su `user_id` o `ristorante_id`**. Fa UPDATE reali. Un admin che corregge una
descrizione comune riscrive la categoria sulle fatture storiche di **tutti i clienti**.

- [ ] Filtro tenant **dentro** la funzione (ha due chiamanti: `admin.py:1541` e `:1657`)
- [ ] Test per mutazione: correzione su un cliente → zero UPDATE sulle fatture di altri

### 1.7 Dropdown categorie

`services/routers/fatture.py:820-855` unisce `categorie_usate` (già filtrate per
`ristorante_id`) alle **canoniche non filtrate**.

- [ ] Non inserire `ARTICOLO DI VENDITA` nella tabella `categorie` (è globale: comparirebbe
      nel menu di ogni ristorante). Compare da sola via `categorie_usate` appena esiste una riga
- [ ] Filtrare le canoniche per settore

---

## Fase 2 — Prompt retail · Opus, ultrathink, ~1 giorno

Verificabile end-to-end **solo dopo 1.4**.

- [ ] Prompt quasi binario: merce da rivendere / spesa di struttura / nota a importo zero,
      scelto per settore dove oggi si usa `PROMPT_CLASSIFICAZIONE_AI`
- [ ] Replicare `tests/test_prompt_ai_coerenza_dominio.py` sul prompt retail: divieto NOTE
      con importo ≠ 0, `Da Classificare` esplicito

---

## Fase 3 — Spegnimenti ed etichette · Opus, ~2 giorni

- [ ] Spenti per retail: ricette (`workspace/foodcost`), coperti (`margini/coperti`),
      **tab Centri di produzione** (`services/routers/margini.py:551-576`: un negozio con
      una sola categoria merce vedrebbe 5 centri a zero con icone 🍖🍷🍰)
- [ ] Radar anomalie resta inerte (`anomaly_radar_service.py:51`, 5 categorie food):
      **accettato e dichiarato** — feature muta per il retail, non un guasto
- [ ] Etichette da dizionario per settore. Centro frontend: `TIPO_SPESA_LABEL`
      (`lib/categorie-spesa.ts:78-81`); poi `TIPO_OPTIONS` in `pivot-tab.tsx` e
      `articoli-tab.tsx`, `margini/calcolo-tab.tsx`, `kpi-bar.tsx`, `analisi-tab.tsx`,
      metadata `app/layout.tsx`, fallback `"Ristorante"` in `app/(app)/layout.tsx:80` e
      `app-sidebar.tsx:108`, **`/m` a mano** (frontend separato, non responsive)
- [ ] Backend/export: `margine_service.py:1173-1175, 1334, 1444` ('Costi F&B', 'Food Cost');
      `routers/margini.py:824-828` ("settore ristorazione", "menù", "porzioni")
- [ ] Tre liste categorie frontend, tutte condivise coi ristoranti: `admin.ts:76-88`
      (`CATEGORIE_TUTTE`, sorgente delle altre), `categorie-spesa.ts:39-45`
      (**aggiungere ARTICOLO qui lo farebbe comparire nel dropdown spese extra dei
      ristoranti: è esattamente la violazione del vincolo**),
      `analisi-fatture/periodi.ts:68-97` (`CATEGORIA_ICONS`: senza voce, appare senza icona)
- [ ] Sei whitelist di scrittura che condividono la costante — `utils/validation.py:525`
      (`valida_categoria_utente`), `routers/fatture.py:884`, `:1059`,
      `routers/admin.py:995`, `:1208`, `:1514`: una funzione `categorie_ammesse(settore)`
      in `settore_service`, non sei `if` copiati

---

## Fase 4 — Briefing, chat AI, soglie · Opus, ~1 giorno

- [ ] Chat: blocco benchmark (`fastapi_worker.py:3552-3628`) — `:3552` dice "Rispondi SOLO
      a domande sui dati del ristorante", `:3618` hardcoda "soglia normale è 28-33%"
- [ ] **Gate tool sul settore, non sulla pagina**: `_TOOL_FLAG` (`:4759-4767`) mappa
      **sia `query_margini` sia `query_coperti` sul flag `margini`** → spegnere i coperti
      via `pagine_abilitate` toglierebbe al negozio anche i margini
- [ ] Briefing: `_CONFIG_TOPICS` (`:2689`) acquisisce la dimensione settore
- [ ] **Bump `_BRIEFING_CODE_VERSION`** o il cliente continua a vedere il testo vecchio
      (cache giornaliera + TTL 30')
- [ ] Soglie: nessun colore per il retail in v1, solo confronto coi mesi precedenti
      (benchmark reali da ~35% abbigliamento a ~78% alimentari: una soglia unica
      colorerebbe di rosso clienti sani)

---

## Fase 5 — Sorveglianza post-deploy · Opus, ~mezza giornata

- [ ] Verifica periodica che confronti le categorie dei ristoranti nel tempo e segnali
      cambi non manuali. Trasforma "l'abbiamo rispettato" in "sappiamo che regge"

---

## Gate di fine fase — nessuna fase si apre senza

Il vincolo si dimostra **sui dati veri dei clienti**, non sui mock.

| # | Controllo | Cosa dimostra |
|---|---|---|
| 1 | `python -m pytest tests/` verde | nessuna regressione nota |
| 2 | `git diff main -- tests/` contiene **solo aggiunte** | nessun test esistente adattato: se serve toccarne uno, la fase si ferma |
| 3 | `python -m pytest -m sql` (164, Postgres vero) | le funzioni SQL — obbligatorio quando si tocca SQL |
| 4 | **Diff a zero** dello snapshot MOL sulle 11 sedi | i numeri dei ristoranti identici al centesimo |
| 5 | **Diff a zero** dello snapshot classificazione | nessuna riga ristorazione cambia categoria |
| 6 | Etichette: ramo ristorazione `==` letterale originale | nemmeno un'etichetta |
| 7 | Mutazione su ogni presidio nuovo: un mutante per volta, nella funzione giusta, `.bak` preso **prima** | il presidio è vero |
| 8 | **Inerenze**: `grep -rn` dei chiamanti **prima** di modificare, elenco nel verbale, ogni chiamante verificato o dichiarato fuori scope | nessun consumatore dimenticato |
| 9 | `/code-reviewer` sulla fase, con le inerenze in mano | seconda lettura indipendente |
| 10 | `export_openapi.py --check-drift`, `check_documentazione.py`, `/chiusura-feature` | chiusa davvero |

I punti 4 e 5 sono **read-only** e girano in un minuto: si rifanno anche a metà fase, ogni
volta che si tocca `ai_service.py`, `margine_service.py` o una funzione SQL.

### I due test che sono il presidio automatico del vincolo

`tests/test_spese_extra.py:238` (`== 29`) e `tests/test_categorie_spesa_frontend.py:92`
(partizione esatta) diventano rossi se `ARTICOLO DI VENDITA` finisce nelle costanti
condivise. **Se diventano rossi, il vincolo di Mattia è violato**: non si adattano, si
torna indietro.

---

## Ordine di deploy — vincolo duro

**La migration si applica sul DB PRIMA del push.** Railway ridispiega a ogni commit (anche
per soli `.md`), e il codice nuovo leggerebbe una colonna inesistente.

Il guasto sarebbe circoscritto, non totale: il worker seleziona sempre colonne esplicite,
mai `*` — `_SEDE_SELECT` (`routers/admin.py:2930`) e `_resolve_sede_attiva`
(`fastapi_worker.py:8036`). Il codice vecchio convive con la colonna nuova senza
accorgersene. Resta un guasto in produzione: l'ordine non cambia.

Sequenza: `apply_migration` → verifica su `information_schema` (tutte le sedi a
`'ristorazione'`) → `CREATE OR REPLACE` delle funzioni SQL → push.

## Tornare indietro

1. **Prima del push** — non esiste per nessuno: si elimina il branch. Costo zero.
2. **Dopo il push, codice** — tag `pre-retail` su `origin/main` (`8acc543`): redeploy di
   quel commit da dashboard, o `git revert` dell'intervallo + push.
3. **Dopo il push, database** — la colonna con default è **inerte** per il codice vecchio.
   Le funzioni SQL riscritte mantengono la firma e, per le sedi ristorazione, devono
   restituire lo **stesso risultato al centesimo**: si prova affiancando una `_v2`,
   confrontandola sui dati veri delle 11 sedi, e solo poi si sostituisce.

Righe `ARTICOLO DI VENDITA` esistono solo per sedi retail, che prima del go-live non
esistono. Un rollback dopo il go-live lascia i negozi con l'interfaccia ristorazione, non
tocca i ristoranti.

---

## Rischi dichiarati

- **Canale ricavi email**: il parser è tarato su `passbi_v1`
  (`worker/email_queue_processor.py:181`); un formato ignoto cade su `_parse_generico` che
  attribuisce **tutto al mittente** (`:190-192`) — per una sede singola va bene, per una
  catena retail è un dato sbagliato silenzioso. Il formato di Passepartout Retail va
  misurato **su un file vero** prima di promettere l'automatismo.
- **Più righe `Da Classificare` per il retail**: senza safety net e senza dizionario. È il
  comportamento giusto per la v1 (regola di dominio #1: meglio in coda che in CARNE), ma
  va detto al cliente in onboarding.
- **Difetto d'ordine nella classificazione**: la cache di `ai_service` è di processo e
  condivisa fra utenti. Esiste **oggi** fra ristoranti. Impatto in misura al 10/9/2026.

---

## Modello per fase

Default Opus. **Fable 5.1** dove l'errore è trasversale e silenzioso sui dati dei clienti,
non dove un test rosso lo segnala subito. A fine fase va detto esplicitamente che è chiusa,
così Mattia cambia modello a mano.

| Fase | Modello | Sforzo |
|---|---|---|
| 0 — snapshot, backup, worktree | Opus | normale — quasi chiusa |
| 1 — isolamento | **Fable** | **ultrathink** — 3 giorni |
| 2 — prompt retail | Opus | **ultrathink** — 1 giorno |
| 3 — spegnimenti ed etichette | Opus | normale — 2 giorni |
| 4 — briefing, chat, soglie | Opus | normale — 1 giorno |
| 5 — sorveglianza | Opus | normale — mezza giornata |

Totale ~7,5 giorni. Fase 1 bloccante per tutte; 3 e 4 indipendenti fra loro.
