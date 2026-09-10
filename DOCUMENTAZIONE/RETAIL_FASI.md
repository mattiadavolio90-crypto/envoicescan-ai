# Retail — le fasi dell'implementazione

Stato al **10/09/2026**: Fase 0 chiusa (commit `b642e3c`), Fase 1 da aprire.

**Questo è il documento unico dell'implementazione**: contesto, decisioni, fatti misurati,
fasi con checklist, gate, deploy, rollback. Il piano di plan-mode
(`~/.claude/plans/mi-piacerebbe-che-l-app-curious-milner.md`) è **superato** da questo
file. Lo stato per riprendere la sessione sta in `docs/piani/PIANO_RETAIL.md` (locale,
git-ignorato): punta qui, non duplica.

> Si aggiorna **durante** il lavoro, non alla fine: le caselle si spuntano quando il gate
> di fase è passato, non quando il codice è scritto. Il nome del file non è casuale: il
> repo ignora `*IMPLEMENTAZIONE*.md` (`.gitignore:79`).

---

## Come si riprende — in quest'ordine, in un processo nuovo

Tutto nel worktree, mai in `/workspaces/ONEFLUX` (che resta su `main` per le sessioni
parallele):

```
cd /home/vscode/ONEFLUX-retail
git branch --show-current                  # deve dire: retail
git log --oneline main..retail             # i commit del lavoro (Fase 0: b642e3c)
git status --short                         # pulito, salvo file di altre sessioni
git rebase main                            # se main è avanzato
python scripts/retail_backup.py --verify   # backup leggibile e allineato al DB
python scripts/retail_baseline.py check    # "Diff a zero", in un processo NUOVO
python -m pytest tests/ -q                 # verde prima di toccare una riga
```

Se `check` non è a zero **prima** di aver toccato codice, sono cambiati i dati o `main`
(altre sessioni, correzioni dei clienti): si ri-cattura con `capture` e si annota il
perché nel verbale — non si "sistema". Se il rebase porta dentro modifiche a
`ai_service.py`, `margine_service.py` o a funzioni SQL, si ri-cattura comunque: la
baseline fotografa il codice, non solo i dati.

---

## Il vincolo, in una riga

I clienti ristorazione non devono vedere **nessun cambiamento, nemmeno un'etichetta**.
Ogni differenza retail è una deviazione che scatta su `tipo_attivita = 'retail'`; il
percorso comune resta letteralmente quello di oggi.

**Regola operativa**: nessuna scrittura sul DB di produzione, in nessuna fase, per nessun
motivo. Solo letture. Le migration si scrivono come file e si applicano **solo al deploy,
per mano di Mattia**. Il 10/9 uno script di snapshot ha creato 308 voci in
`prodotti_utente` su 4 clienti reali (cancellate, DB riportato allo stato esatto e
verificato contro backup): è la ragione dei presidi in `scripts/retail_baseline.py`.

**Dove si lavora**: branch `retail` nel worktree `/home/vscode/ONEFLUX-retail`.
Mai su `main`: il push serale spedisce tutto `main`, e un retail a metà significherebbe
codice che legge `tipo_attivita` prima che la migration esista. È l'unica ragione che
`WORKFLOW.md` §1 ammette per un branch — il lavoro potrebbe non essere spedito.

---

## Contesto e decisioni — non si ridiscutono senza motivo

ONEFLUX è **controllo di gestione, non analitica di vendita**: non ha il venduto per
articolo nemmeno per i ristoranti, e funziona lo stesso. Il conto economico — fatturato →
costo merce → primo margine → spese generali → personale → MOL — è identico per un negozio,
e il motore economico è già neutro (la RPC del MOL usa un catch-all, vedi «Verificato»).
Il cliente retail ha già il suo gestionale di cassa per il venduto; da ONEFLUX vuole i costi.

Decise da Mattia nel brainstorming del 7/9 e nelle revisioni del 10/9:

- **Una sola categoria merce, `ARTICOLO DI VENDITA`**, più le 4 spese generali esistenti.
  Niente tassonomia retail da progettare, niente 1.280 keyword da riscrivere. La
  profondità d'analisi (un ferramenta, una libreria) la danno i **tag custom**, che
  esistono già con KPI, trend e fornitori (`services/tag_analytics_service.py`) e si
  auto-suggeriscono.
- **Il nome**: «MERCE» è inutilizzabile — le keyword di sconti/resi sono cercate per
  sottostringa (`utils/validation.py:362-374`). «COSTO DEL VENDUTO» è sbagliato — in
  contabilità è acquisti ± rimanenze, non righe di fattura. «ARTICOLO DI VENDITA» non
  collide: il confronto sulle descrizioni generiche è per parola intera o su max 2 token
  (`upload_handler.py:490-493`).
- **Incidenza merce** (l'ex food cost %) resta accesa, rinominata. Non si spegne.
- **Ricette e coperti spenti.** Coperti: la cassa manda solo il fatturato, lo scontrino
  medio non è calcolabile — rietichettare non ha senso.
- **Nessuna soglia di colore per il retail in v1**: i benchmark reali vanno da ~35%
  (abbigliamento) a ~78% (alimentari), una soglia unica colorerebbe di rosso clienti sani.
  Solo confronto coi mesi precedenti.
- **Account omogenei in v1**: tutte le sedi di un utente hanno lo stesso settore. Un
  proprietario con ristorante *e* negozio usa due account. Elimina quattro interventi
  (propagazione della sede nel parsing, `prodotti_utente` per sede, gating per sede,
  riparto misto). Misti rimandati a v2; il campo resta sulla sede per non chiudere la porta.
- **Nessun test esistente si modifica.** Se per far passare la suite serve toccarne uno,
  ho cambiato un comportamento ristorazione: la fase si ferma.
- **Misurare prima il difetto d'ordine** (10/9): fatto, impatto zero, derubricato.

### Misurato sul DB vivo — 10/9/2026

| Cosa | Valore |
|---|---|
| Sedi | 12, di cui **11 con fatture** (IL BARETTINO ha 0 righe; «Ambiente Test Admin» sono due sedi omonime di test) |
| Utenti con sedi | 7 |
| Utenti multi-sede | 2 — OFFSIDE (3 sedi, **di cui 1 tecnica**) e SUSHILAND (4 sedi). Entrambi omogenei |
| Righe fattura attive | 39.515 |
| `prodotti_utente` | 5.384 (di cui 1.393 correzioni manuali dei clienti) |
| `prodotti_master` | 2.913 |
| `classificazioni_manuali` | 4 |
| Categorie canoniche | 31 |
| `ristoranti.tipo_attivita` | non esiste |

Se queste cifre cambiano, la baseline va ri-catturata prima di confrontare.

### Tre premesse del primo piano erano sbagliate

Verificate sul codice vivo il 10/9, non dedotte. Vanno sapute perché il ragionamento
"ovvio" porta esattamente lì:

1. **«La riga scartata prosegue verso l'AI dentro `categorizza_con_memoria`»** — falso.
   Quella funzione (`ai_service.py:4905-5182`) **non chiama mai l'AI**: finisce sul
   dizionario. L'AI sta in `classifica_con_ai` (`:5434`), in un altro momento del flusso.
   Il canale reale è restituire `Da Classificare` con `is_fallback=True`.
2. **«Due definizioni di costi merce → due MOL diversi in pagina»** — falso. La RPC
   `costi_automatici_mensili` riceve `p_cat_food` e **lo ignora** (nel corpo compare solo
   `p_cat_spese`); `margine_service.py:137-141` è catch-all allo stesso modo. Il MOL del
   retail è corretto senza toccare nulla. Le whitelist chiuse alimentano il tab Centri e
   il riparto di catena: una fase intera («unificare le whitelist») è sparita.
3. **La validazione dell'output AI non era nel piano** — `ai_service.py:5412` scarta ogni
   categoria fuori da `TUTTE_LE_CATEGORIE`. Senza toccarla, il prompt retail non
   produrrebbe nulla e il sintomo sarebbe indistinguibile da «il prompt non funziona».

Trovati nello stesso giro, non previsti: la propagazione storica **senza filtro tenant**
(1.6, esiste oggi fra ristoranti), la sede tecnica creata da SQL (1.1), il gate dei tool
chat che accoppia coperti e margini (Fase 4). E i numeri di riga del piano erano scivolati
(`categorizza_con_memoria` 4885→4905, `_CENTRI_DI_PRODUZIONE` 8269→8366): **si ri-misurano,
non si ereditano**.

### Verificato: regge senza lavoro

- RPC `costi_automatici_mensili` catch-all in produzione (misurato su `pg_proc`): il MOL
  retail è corretto per costruzione.
- `enforce_no_unclassified_category` (`ai_service.py:708`) restituisce `Da Classificare`,
  **non** SERVIZI: regola di dominio #1 rispettata anche per il retail.
- Constraint su `fatture.categoria`: solo non-vuoto, nessun CHECK enumera le categorie.
- `_tipo_da_categoria` (`routers/workspace.py:2328`) e `tipoDaCategoria`
  (`lib/categorie-spesa.ts:49`) sono **entrambe catch-all**: `ARTICOLO DI VENDITA` cade
  nel secchio giusto da sola su entrambi i lati.
- **Trigger DB: nessun rischio** — gli unici che toccano la categoria loggano
  (`trg_log_category_change_fatture`) o invalidano cache (`trg_bump_cache_pm`); nessuno
  filtra per valore. **Nessuna vista SQL** contiene whitelist food.
- **Indice di salute**: le sue 4 voci sono neutre rispetto al settore.
- Divisioni per zero protette; export Excel con colonne derivate dai dati.
- Tab Categorie per retail: 5 fette (articoli + 4 generali), leggibile.
- **Difetto d'ordine nella classificazione: non esiste sui dati reali** (misura sotto).

---

## Fase 0 — Snapshot di riferimento e messa in sicurezza · **CHIUSA** 10/9/2026

- [x] Worktree `/home/vscode/ONEFLUX-retail` su branch `retail`
- [x] Tag `pre-retail` su `origin/main` (`8acc543`); `main` allineato, 0 commit in coda
- [x] Backup 5 tabelle in `~/oneflux-backup/20260910_105630` (3,3 MB), verificato nel
      contenuto (non solo nei conteggi): 1.393 correzioni manuali presenti, riga campione
      identica al DB. Script: `scripts/retail_backup.py` (`--verify` per ricontrollare)
- [x] Cifre del piano ri-misurate sul DB vivo (tabella sopra)
- [x] `scripts/retail_baseline.py` di sola lettura, **due presidi indipendenti**,
      provato per mutazione: delta 0 su `prodotti_utente` e `prodotti_master`
- [x] Misura dell'impatto del difetto d'ordine: **zero**
- [x] Snapshot riproducibile: **5 check verdi consecutivi** in processi separati
- [x] Verbale (questo documento) + commit `b642e3c`

### Impatto del difetto d'ordine: misurato, è zero

In sola lettura, su **tutte le sedi con dati**. Ogni sede classificata due volte con lo
stesso campione di righe reali: (A) da sola con cache azzerata, (B) dopo tutte le altre
sedi — il caso peggiore del worker in produzione, che elabora più clienti nello stesso
processo.

**0 divergenze su 3.075 righe di campione, in 10 sedi su 10** (CASATI 14 400, Costi comuni
di gruppo 316, LAND DEI SAPORI 400, OFFSIDE 400, OVERTIME 284, SUSHILAND Mariano 400,
San Giuliano 400, Villa Guardia 400, TIME CAFE 400, Ambiente Test Admin 75+75).

Le 11 divergenze viste su Villa Guardia la mattina del 10/9 erano un artefatto della
cattura senza `_azzera_cache_memoria()` prima di ogni sede, non un difetto vivo. Resta vero
che la cache di `ai_service` è di processo e condivisa fra utenti, ma sui dati reali non
produce effetti. **Nessuna correzione da fare prima del retail.**

### Snapshot riproducibile: verificato

Provato nel suo uso reale — `capture` in un processo, `check` in processi nuovi e separati:
**cinque check consecutivi a «Diff a zero: 56 righe di costi e 3475 categorie invariate»**.

Determinismo provato per costruzione, non assunto: tre processi identici sulla stessa sede
→ 0 divergenze; due catture complete nello stesso processo → 0; N sedi precedenti
(0, 1, 2, 3, 5, 8) prima della sede target → 0; lettura paginata di `prodotti_utente`,
20 esecuzioni → 3.067 righe sempre, con e senza `ORDER BY`.

**Un fatto resta non spiegato**: la prima baseline delle 10:58 divergeva su 24 righe
(22 San Giuliano, 2 Villa Guardia), tutte in una direzione — la baseline diceva
`Da Classificare`, il ricontrollo risolveva; solo 4 venivano dalla memoria locale, 20 dal
dizionario che non dipende da stato. Sei ipotesi (polling `cache_version`,
`_brand_union_cache`, proxy di sola lettura, `_loaded_user_ids`, paginazione senza
`ORDER BY`, baseline obsoleta) **tutte testate e tutte scartate** con misure. La baseline è
stata ri-catturata ed è verde in modo ripetibile, che è la proprietà che serve al gate.
Se una divergenza a senso unico verso `Da Classificare` ricompare, questo è il primo
sospetto da riaprire.

**Regola operativa che ne consegue**: la baseline si ri-cattura **all'inizio di ogni fase**
e il `check` si esegue **in un processo nuovo**, mai riusando un processo che ha già
catturato. Un `check` verde una volta sola non è una prova: se ne fanno **due**.

---

## Fase 1 — Isolamento · **bloccante per tutte le altre** · Fable, ultrathink, ~3 giorni

Nessuna fase successiva parte prima che questa abbia passato il gate. Sottofasi
nell'ordine: ogni casella si spunta col gate 4-5 (baseline) rifatto.

### 1.1 Migration e perno

- [ ] `supabase/migrations/AAAAMMGGHHMMSS_add_tipo_attivita.sql`:
      `ALTER TABLE ristoranti ADD COLUMN tipo_attivita TEXT NOT NULL DEFAULT 'ristorazione'`
      + `CHECK (tipo_attivita IN ('ristorazione','retail'))`. **Si scrive, non si applica.**
- [ ] **Ereditarietà della sede tecnica**: l'INSERT dentro `assegna_fattura_a_sede_tecnica`
      (`supabase/schema_snapshot.sql:1614-1621`) elenca 6 colonne e non include
      `tipo_attivita` → su un account retail la sede tecnica nascerebbe `'ristorazione'`.
      Copiare il valore dalla stessa sede reale da cui già copia la P.IVA. Anche questa è
      SQL nella stessa migration (`CREATE OR REPLACE`), stessa firma
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
Non è un problema retail: è un fix per i clienti attuali, e va **detto a Mattia** quando
si chiude.

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
| 5 | **Diff a zero** dello snapshot classificazione (3.475 righe) | nessuna riga ristorazione cambia categoria |
| 6 | Etichette: ramo ristorazione `==` letterale originale | nemmeno un'etichetta |
| 7 | Mutazione su ogni presidio nuovo: un mutante per volta, nella funzione giusta, `.bak` preso **prima** | il presidio è vero |
| 8 | **Inerenze**: `grep -rn` dei chiamanti **prima** di modificare, elenco nel verbale, ogni chiamante verificato o dichiarato fuori scope | nessun consumatore dimenticato |
| 9 | `/code-reviewer` sulla fase, con le inerenze in mano | seconda lettura indipendente |
| 10 | `export_openapi.py --check-drift`, `check_documentazione.py`, `/chiusura-feature` | chiusa davvero |

I punti 4 e 5 sono **read-only** e girano in pochi minuti: si rifanno anche a metà fase,
ogni volta che si tocca `ai_service.py`, `margine_service.py` o una funzione SQL. Il
`check` va in un processo nuovo, e verde **due volte** prima di dichiararlo.

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
4. **Dati** — backup delle 5 tabelle di memoria/anagrafica in `~/oneflux-backup/`
   (`scripts/retail_backup.py`). **Non esiste uno script di ripristino**, di proposito:
   sarebbe una scrittura in produzione, e si scrive solo se e quando serve, con dry-run e
   `salta_correzioni_manuali`, su decisione di Mattia. Le `fatture` non sono nel backup:
   nessuna fase le scrive; se una dovesse, il backup si estende **prima**.

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
- **Rientro** (retail → ristorazione): le righe `ARTICOLO DI VENDITA` restano, cadono nel
  catch-all (MOL corretto) e nel secchio "fb" (coerente). Il cliente vede una categoria in
  più. Accettabile.
- **`test_documentazione_onesta.py` non scansiona questo file** (lista fissa di documenti):
  finché resta sul branch può mentire senza che un test lo dica. Al merge su `main` va
  aggiunto alla lista, o i suoi riferimenti a simboli e righe vanno ri-misurati a mano.

---

## Chiusura finale — quando tutte le fasi hanno passato il gate

- [ ] `git rebase main` e suite verde sul cumulativo
- [ ] `/code-reviewer` sul cumulativo del branch, non solo sull'ultima fase
- [ ] Baseline: `capture` su `main` aggiornato, poi `check` sul branch → zero
- [ ] `CLAUDE.md`: una riga su `tipo_attivita` nelle regole di dominio;
      `tests/test_documentazione_onesta.py`: questo file nella lista (l'indice §6 di
      `MAPPA_TECNICA.md` lo cita già dal 10/9)
- [ ] Migration applicata sul DB **prima** del push, per mano di Mattia (sequenza sopra)
- [ ] Commit portati su `main` con rebase (non merge), branch eliminato, worktree rimosso
- [ ] Memoria di progetto aggiornata, `docs/piani/PIANO_RETAIL.md` eliminato
      (`WORKFLOW.md` §2: mai due fonti sullo stesso stato)

---

## Modello per fase

Default Opus. **Fable 5.1** dove l'errore è trasversale e silenzioso sui dati dei clienti,
non dove un test rosso lo segnala subito. A fine fase va detto esplicitamente che è chiusa,
così Mattia cambia modello a mano.

| Fase | Modello | Sforzo |
|---|---|---|
| 0 — snapshot, backup, worktree | Opus | **chiusa** 10/9 (`b642e3c`) |
| 1 — isolamento | **Fable** | **ultrathink** — 3 giorni: 4 file condivisi, 12 punti di uscita, il fix tenant sulle fatture di tutti |
| 2 — prompt retail | Opus | **ultrathink** — 1 giorno: regola di dominio #1 |
| 3 — spegnimenti ed etichette | Opus | normale — 2 giorni |
| 4 — briefing, chat, soglie | Opus | normale — 1 giorno |
| 5 — sorveglianza | Opus | normale — mezza giornata |

Totale ~7,5 giorni. Fase 1 bloccante per tutte; 3 e 4 indipendenti fra loro.
