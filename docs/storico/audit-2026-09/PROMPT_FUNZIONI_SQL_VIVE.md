# Prompt sessione — Chiudere i residui dei Punti 2 e 3, poi le 17 funzioni SQL che nessun test esegue

> **Modello**: **Opus**, `ultrathink` in apertura — le funzioni della Parte B
> calcolano numeri che il cliente vede in pagina (spesa per tag, pivot del
> gruppo, articoli da fatture, limite della chat). Normale sull'esecuzione.
> **Sforzo**: alto. La Parte A è corta ma va chiusa **prima**, o la Parte B
> parte da uno snapshot che non è il live.
> **Documento vivo**: `DOCUMENTAZIONE/AUDIT_ULTIMO_PERIMETRO.md` (ignorato da
> git, sta su disco). Il contatore `AUDIT_COPERTURA.md` è **archiviato** in
> `docs/storico/audit-2026-09/` e non si aggiorna: le cifre vanno nel vivo.
> **Stato repo alla stesura (08/09/2026, ore 15:40)**: HEAD `2105d44`,
> **albero pulito (0 file)**, **coda push 2** (il Punto 3 è committato, NON
> spedito; la sua migration **è applicata** al live, lo **snapshot no** — è
> esattamente il lavoro di A1), suite **13.180 verdi + 44 skip** su copia
> pulita (119 SQL inclusi, ri-verificati verdi alle 15:40), copertura
> **letta 97%**, **eseguita 61%** del backend.

> ---
>
> ## ESEGUITO E CHIUSO — 08/09/2026, sera
>
> **Parte A: chiusa.** BL-2 (snapshot allineato a mano, `e5efb21` + `5b2d58d`),
> BL-1 (presidio sulla paginazione di `categoria_batch`, `e93d6ff`), verbale e
> review verde sul cumulativo.
>
> **Parte B: 8 funzioni su 17**, il perimetro di Livello 1 deciso da Mattia
> (`1df7678` + `a4efadf`). Le 9 di Livello 2 restano scoperte e dichiarate.
> Test SQL 119 → 164; suite 13.237 verdi.
>
> **Tre correzioni a questo prompt, misurate mentre lo eseguivo** — chi lo
> rilegge non erediti le cifre sbagliate:
>
> 1. **«Le 4 funzioni divergono dal live»**: ne divergeva **una sola**
>    (`fn_log_category_change`, la costante `c_uuid` inlineata). Le altre tre
>    coincidevano già — verificate una per una con `pg_get_functiondef`.
> 2. **«35 di servizio»**: contandole per prefisso sullo snapshot sono **22**, e
>    le funzioni mai classificate sono **24**, non 11. Le «17 vive» erano il
>    perimetro di questo prompt, **non l'inventario del database**.
> 3. **«Nessuna delle 17 ha test»**: vero per l'*esecuzione*, ma 6 su 8 del
>    Livello 1 avevano già test che **mockano** il client o **leggono il file**
>    della migration. Difendevano cose vere; un errore nel corpo SQL passava.
>
> **Due cose trovate che il prompt non prevedeva**, entrambe da decidere:
> la divergenza fra le tre RPC della pagina Tag su `Da Classificare` (12 chiavi,
> 5 sedi, 3.052,27 € potenziali; caso peggiore `COMMISSION` di San Giuliano,
> 33% di scarto) e il limite chat che azzera a mezzanotte **UTC**.
>
> Verbale completo: `DOCUMENTAZIONE/AUDIT_ULTIMO_PERIMETRO.md`.

---

## ⚠️ Prima di tutto: ri-misura, non ereditare

Ogni cifra qui è misurata l'**08/09/2026** su HEAD `07157be` e sul DB live.
In questo progetto le premesse dei prompt sono state smentite dalla misura in
**6 casi su 12**: il prompt del Punto 3 diceva 41 script scrittori, erano
**19** (il grep contava anche `sys.path.insert`). Ri-misura comunque.

```bash
git log --oneline origin/main..main       # atteso: 2 commit, o 0 se Mattia ha già spedito
python -m pytest -q -m sql                # 119, devono essere verdi
python scripts/check_documentazione.py
git status --short                        # file NON tuoi sono lo stato atteso: contali, non toccarli
```

Se i test SQL non sono verdi **non è un problema dei test**: o lo snapshot è in
drift rispetto al DB live, o una migration nuova non si applica sopra. La
fixture lo dice nel messaggio d'errore.

---

## Parte A — Chiudere davvero i Punti 2 e 3 (residui misurati)

Due review con verdetto 🔴 hanno lasciato tre cose aperte. Sono **corte** e
vanno chiuse **in quest'ordine**, perché A1 cambia il DB su cui gira tutto il
resto.

### A1. Lo snapshot va allineato **a mano, ma per bene** (BL-2)

**La migration del Punto 3 è già applicata al live** — verificato l'08/09 su
`pg_proc`: `aggiorna_categoria_fatture_attribuita` ha **una sola** firma, a 8
argomenti, `SECURITY DEFINER`, `search_path=public`, `anon` e `authenticated`
senza EXECUTE, `service_role` sì. Non rifarlo: ri-verificalo con la stessa
query e passa oltre.

Quello che resta storto è `supabase/schema_snapshot.sql`. Va allineato **a
mano**: `scripts/genera_schema_snapshot.py` richiede `SUPABASE_DB_URL` (la
password Postgres del progetto), che **non è disponibile** — decisione di
Mattia dell'08/09, presa sapendo il costo. Non chiedergliela di nuovo e non
provare a recuperarla: si fa a mano.

**Cosa c'è di storto oggi**, misurato confrontando lo snapshot col catalogo
live (`pg_get_functiondef`):

| Punto | Snapshot | Live |
|---|---|---|
| `fn_log_category_change`: costante UUID | letterale regex inlineato nei 2 usi | `c_uuid CONSTANT TEXT := '...'` dichiarata |
| `fn_log_category_change`: commenti | ha `-- Accesso SICURO ai campi...` | il catalogo non li restituisce |
| Ordine delle funzioni | `_azzera_attribuzione_categoria` in cima al blocco | le IMMUTABLE per prime, poi plpgsql, poi `sql`, poi i trigger |
| Riga `-- Rigenerato il` | `2026-09-09` (data futura) | — |

**Come si fa a mano, senza rompere l'ordine.** Lo script ordina le funzioni
con `Q_FUNZIONI` (`scripts/genera_schema_snapshot.py`, ~riga 186), e l'ordine
**non è estetica**: una funzione `LANGUAGE sql` che ne chiama un'altra esige
che quella esista già, quindi le `sql` vanno dopo le `plpgsql`, le IMMUTABLE
per prime, i trigger in fondo. Se sposti una funzione a caso, il DB dei test
non si costruisce più.

1. Per ogni funzione toccata dai Punti 2 e 3 (`fn_log_category_change`,
   `aggiorna_categoria_fatture_attribuita`, `aggiorna_categoria_prodotto_attribuita`,
   `_azzera_attribuzione_categoria`), prendi il corpo **dal live** con
   `SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = '...'`
   (MCP Supabase, sola lettura) e incollalo **al posto** di quello nello
   snapshot, alla **stessa posizione** in cui si trova adesso — non spostarlo.
2. `_azzera_attribuzione_categoria` è l'unica fuori posto: è `plpgsql`
   VOLATILE e sta in cima al blocco, prima delle IMMUTABLE. Spostala dopo di
   quelle, in ordine alfabetico fra le plpgsql. Verifica che il DB di test si
   monti ancora (i 119 test SQL girano, o l'ordine è sbagliato).
3. **Correggi la riga della data**: `-- Rigenerato il 2026-09-08.` (oggi,
   non domani). La fixture (`tests/conftest_sql.py`) usa quella data come
   taglio: applica sopra lo snapshot ogni migration con prefisso `>=`. Con
   `2026-09-09` la migration `20260909090000` viene ri-applicata (innocuo,
   è idempotente) ma la data mente.
4. **Correggi le altre date «09/09» → «08/09»**: sono **13 occorrenze in 7
   file**, ri-contate alle 15:40 (il primo giro ne aveva viste 4 — ri-misura
   con `grep -rc`, non fidarti di questa lista):

   | File | Occorrenze |
   |---|---:|
   | `tests/test_ricategorizza_sede_pipeline.py` | 5 |
   | `scripts/ricategorizza_sede.py` | 2 |
   | `supabase/migrations/20260909090000_guardia_righe_arbitrate.sql` | 2 |
   | `services/db_service.py` | 1 |
   | `scripts/ricategorizza_sede_ai.py` | 1 |
   | `tests/test_registro_correzioni_chokepoint.py` | 1 |
   | `tests/test_sql_registro_correzioni.py` | 1 |

   Sono **commenti e docstring**, non codice: la modifica non cambia il
   comportamento, ma va fatta con la suite verde dopo (una docstring citata da
   un test esiste). **Il nome del file della migration non si tocca**: è già
   applicata al live con quel nome, e rinominarla la farebbe ri-applicare.
5. **Ricontrolla che i test mordano ancora**: neutralizza la guardia
   (`NOT p_salta_arbitrate` → `true`) **sia nello snapshot sia nella
   migration** — la fixture ri-applica la migration sopra lo snapshot, quindi
   mutare solo uno dei due non misura niente — e verifica che
   `tests/test_sql_registro_correzioni.py` vada rosso (l'08/09: 3 test).
   Ripristina, `git status` pulito.
6. **Scrivi nello snapshot, in testa, che è stato allineato a mano** e perché
   (nessuna `SUPABASE_DB_URL`), con la data. L'intestazione oggi dice «NON
   modificare a mano: rigenerare» e chi arriva dopo deve sapere che la regola
   è stata sospesa consapevolmente, non violata per distrazione.
7. Un commit solo: snapshot + date.

> **Perché non basta «tanto è equivalente».** Oggi le due versioni di
> `fn_log_category_change` fanno la stessa cosa, quindi non c'è un guasto in
> vista. Ma i 119 test SQL girano sullo snapshot: da qui in poi «i test SQL
> sono verdi» prova qualcosa solo se lo snapshot è il DB vero. La prossima
> divergenza sarà indistinguibile da questa.

### A2. Il fix più grave del Punto 2 non ha rete (BL-1)

`services/routers/fatture.py`, `categoria_batch`: le due select che precedono
la scrittura usano `fetch_all` (riga **913** e riga **930**, ramo NOTE E
DICITURE) perché PostgREST tronca a **1000 righe senza errore** e sul live una
descrizione su una sede è già a **930 righe**. Rimettendo `.execute().data`
al posto di `fetch_all(...)` **la suite intera resta verde: 13.167 passati, 0
rossi** (misurato dal reviewer l'08/09, mutante singolo, copia pulita).

Serve un test che **esegua** `categoria_batch` con più di 1000 righe candidate
e muoia su quel mutante — su **entrambe** le righe. Metti il test in un file
nuovo: `tests/test_registro_correzioni_chokepoint.py` è stato riscritto dal
Punto 3 e non è il posto. Provalo per mutazione: backup **prima**, un mutante
per volta, `diff` per vedere che la mutazione sia avvenuta, `git status`
pulito alla fine.

### A3. Verbale e contatore

Nel documento vivo: Punti 2 e 3 **chiusi con review verde** (finora sono
«chiusi sul codice»: il registro ha **0 righe dal deploy** — ultima scrittura
03/09 — e nessuna riga attribuita vera esiste ancora; la prima che compare
con `source='worker_coda'` è la conferma, va guardata, non assunta). Poi
`/code-reviewer` sul cumulativo A1+A2 **prima** di aprire la Parte B: la
lezione dell'08/09 è che una review sul primo commit non copre i fix che
seguono.

---

## Parte B — Le 17 funzioni SQL vive che nessun test esegue

### Il problema, misurato

Sul live: **75 funzioni** `public`, **26 trigger**, **96 policy**. Snapshot e
live coincidono per nome (drift 0 — ma vedi A1 per il corpo). I test SQL
(`tests/test_sql_*.py`, 119 test) **eseguono** 21 funzioni per nome più i 2
pezzi del registro esercitati dal trigger. Delle 52 restanti, **35 sono
trigger di orario e job di pulizia** (`update_*_timestamp`, `set_*_updated_at`,
`fn_bump_cache_version*`, `purge_*`): non muovono numeri, non entrano qui.

**Le 17 che restano sono tutte vive** (ogni nome ha almeno un chiamante in
`services/`, `worker/` o `apps/web/src/`) e **calcolano o registrano
numeri**. Nessuna è mai stata eseguita da un test.

### Livello 1 — le 8 che il cliente vede in pagina (prima)

| Funzione | Chi la chiama | Cosa decide |
|---|---|---|
| `articoli_da_fatture` | `services/foodcost_service.py`, `services/db_service.py`, `services/routers/workspace.py` | gli articoli e i prezzi da cui parte il foodcost |
| `gruppo_spesa_pivot` | `services/routers/gruppo.py`, `services/fastapi_worker.py` | il pivot di spesa del gruppo (per sede × categoria) |
| `gruppo_tag_trend` | `services/routers/gruppo.py` | l'andamento della spesa per tag |
| `gruppo_tag_fornitori` | `services/routers/gruppo.py` | la spesa per tag ripartita sui fornitori |
| `gruppo_tag_descrizioni` | `services/routers/gruppo.py`, `apps/web/src/lib/tag-candidati.ts` | le descrizioni candidate per un tag (entra nel frontend) |
| `gruppo_salute_componenti` | `services/routers/gruppo.py` | il semaforo di salute per sede |
| `chat_top_categoria_fornitore` | `services/fastapi_worker.py` | la risposta della chat su «chi mi costa di più» |
| `chat_usage_check_and_log` | `services/fastapi_worker.py` | **il limite giornaliero della chat** — azzera a mezzanotte **UTC** (01:00/02:00 italiane). È una divergenza **nota e non decisa** (07/09): il test documenta il comportamento di oggi, **non lo cambia** senza Mattia |

### Livello 2 — le 9 di staff e costi AI (dopo, stessa sessione)

`admin_ai_mensile`, `admin_consumi_mensili`, `admin_conteggio_fatture`,
`admin_fatture_per_mese`, `get_ai_costs_summary`, `get_ai_costs_timeseries`,
`get_ai_recent_operations`, `increment_ai_cost`, `track_ai_usage_event`.
Sbagliate danno un numero storto a Mattia, non al cliente: dopo le 8, non
prima. Se il tempo finisce, **dichiaralo** nel verbale: «17 di cui N provate»,
con i nomi.

### Come si prova una funzione SQL, qui

Il modello è `tests/test_sql_funzioni_soldi.py` (07/09): fixture
`db_sql`/`sql`/`scalare` da `tests/conftest_sql.py`, **semina righe vere**
(fatture con `deleted_at IS NULL` e qualcuna cancellata, più sedi, più mesi,
una categoria `Da Classificare`), **chiama la funzione**, **asserisce sul
numero** — e, dove esiste il gemello Python (`gruppo_spesa_pivot` ↔
`services/routers/gruppo.py`), confronta i due risultati sugli stessi dati:
il 07/09 il confronto SQL↔Python sulle formule del MOL ha dato «identiche»,
ed è l'unico modo per dirlo.

- **Mai asserire sul testo del corpo** (`pg_get_functiondef`): un mutante che
  cambia il comportamento lascia il testo intatto e sopravvive.
- **Mai su un aggregato solo**: la somma resta giusta se due componenti
  sbagliate si annullano. Asserisci le parti.
- **Soft delete e `Da Classificare`**: ogni funzione che aggrega `fatture`
  deve escludere `deleted_at IS NOT NULL`; le funzioni che alimentano margini
  devono escludere `Da Classificare` (regola di dominio #1). Semina entrambi i
  casi e verifica che **non** entrino.
- **Permessi**: ogni `SECURITY DEFINER` entra in
  `tests/test_sql_funzioni_permessi.py` — `anon` e `authenticated` non devono
  poter eseguire. Il 07/09 due funzioni erano eseguibili con la chiave
  pubblica e la prima `REVOKE ... FROM PUBLIC` non le chiudeva: su Supabase
  la revoca va **nominale** (`FROM PUBLIC, anon, authenticated`).
- **Prova per mutazione, o non è un presidio**: backup **prima** del primo
  mutante, **uno per volta**, `diff` per vedere che sia applicato, e controlla
  **in quale funzione** cade il pattern (lo stesso `WHERE` vive in più corpi).
  L'08/09 tre mutanti su sei non si erano applicati e mostravano «8 passed».
- Se una funzione risulta **sbagliata**: misura l'impatto sul live (quante
  sedi, quanti euro) **prima** di correggerla, e la correzione è una migration
  nuova in `supabase/migrations/` (`AAAAMMGGHHMMSS_nome.sql`) applicata al
  live **con snapshot rigenerato nello stesso commit** — vedi A1.

---

## Lo stato dell'app in una tabella — cosa è coperto e cosa no

Misurato l'08/09/2026 a `24b0ae0`. **Ri-misuralo**, non ereditarlo.

| Perimetro | Righe | Stato |
|---|---:|---|
| Backend Python (`services/`, `utils/`, `config/`, `worker/`) | 57.297 | **100% guardato** — metà letto riga per riga, metà sotto una lente sola |
| Frontend (`apps/web/src/`) | 53.955 | 94% — **3.316 righe mai guardate**, tutte in aree che non muovono denaro (agenda, assistenza, style-guide, login, legali, gusci, CSS) |
| Edge Functions | 3.556 | 100%, 101 test Deno |
| **Totale app** | **114.808** | **111.492 coperte (97%)** |
| **Logica SQL dentro il DB** | 75 funzioni, 26 trigger, 96 policy | **mai nel contatore** — è il lavoro di questa sessione |

Due numeri, due significati diversi: **97% è quanto è stato *letto*; 61% è
quanto viene *eseguito* dai test** (`coverage`, backend, misurato l'08/09 —
24.281 righe eseguibili, 8.950 mai toccate). Dove passano i soldi la rete è
densa (`riparto` 94%, `personale_export` 96%, `margine_service` 85%); dove non
si è lavorato si vede (`routers/tag.py` 35%, `upload_handler` 40%,
`db_service` 43%). **Alzare quelle percentuali non è un ciclo dedicato**: si fa
quando si tocca il file.

**Cosa resta scoperto, in ordine di rischio:**

1. **Le 17 funzioni SQL** di questa sessione — il DB non è mai stato contato.
2. **`routers/` a copertura parziale**: 16.967 righe, ~5.400 lette. Sicurezza
   chiusa (216 endpoint su 216), logica no. Prossimo candidato `fatture.py`.
3. **3.316 righe di frontend mai guardate**: nessuna muove denaro, ed è
   **l'ultima priorità**, non la prima.
4. **Il rendering del frontend non è testabile per scelta**: nessun runner npm
   (`deploy-vercel.yml` scatta su `apps/web/**`, un runner deployerebbe a ogni
   test). 42.293 righe di `.tsx` fuori portata, 11.366 di logica pura dentro.
   È un limite d'impianto **accettato**, non un buco da chiudere.

---

## Fuori perimetro — decisioni di Mattia, non tue

Emersi dal Punto 3, **non aprirli di iniziativa**: nominali nel verbale e
chiedi. Se Mattia dice sì, sono lavoro della stessa classe di questa sessione.

1. **`_propaga_global_override_a_fatture_storiche`** (`services/ai_service.py`,
   riga ~4511) scrive cross-tenant e si difende leggendo la **memoria**
   (`prodotti_utente.classificato_da`), non `fatture.categoria_fonte` /
   `reviewed_at`: le 318 righe riviste a mano senza voce in memoria restano
   raggiungibili. Mai usata in produzione (0 righe con
   `reviewed_by='admin-global-propagation'`), ma è la guardia del Punto 3
   aggirata da un percorso applicativo.
2. **`scripts/_recalc_review_sushiland.py`** scrive `needs_review` senza
   guardia: può rimettere in coda una riga arbitrata.
3. **17 script monouso** in `scripts/` (1 commit, aprile–giugno): il Punto 3
   ne ha cancellato uno (`catscan_applica.py`, era morto) e contato **15
   scrittori**. Elenco misurato l'08/09: `backfill_totali_fatture`,
   `audit_category_change_log`, `audit_prodotti_utente_conflicts`,
   `backfill_prodotti_utente_normalize`, `kpi_fallback_review`,
   `backfill_documenti_da_cartella`, `find_user_id`, `run_migration_079`,
   `audit_fra_diclemente`, `audit_fra_enrich`, `audit_processo_classificazione`,
   `catscan_arbitro`, `catscan_freddo`, `catscan_senza_segnale`,
   `chat_eval_diagnosi`, `test_accettazione_import`, `_recalc_review_sushiland`.
   Alcuni sono **sola lettura** (gli `audit_*`, `catscan_freddo`,
   `catscan_senza_segnale`): «monouso» non vuol dire «scrittore». Si cancellano
   dopo il sì, non prima.
4. **`prodotti_utente` resta cieca nel registro** (110 righe anonime): la RPC
   gemella esiste ed è testata, ma gli `upsert` non possono impostare i GUC.
   È lavoro suo, non un parametro in più.
5. Le due divergenze del 07/09: `data_competenza` vs `data_documento` (229
   righe, 3.794 €, 1 sede) e il limite chat in UTC.

---

## Vincoli da rispettare

- **Regole di dominio #1 e #2** (`Da Classificare`; `NOTE E DICITURE` solo con
  `totale_riga == 0`). Ogni scrittura di `categoria` su `fatture` passa da
  `aggiorna_categoria_fatture` (`services/db_service.py`) con `source` e
  `batch_id`; uno script che scrive per conto d'altri accende
  `salta_correzioni_manuali=True`; la correzione del cliente **no**.
- **Mai `git add -A`**: più sessioni girano in parallelo, e file non tuoi
  sono lo stato atteso, non un allarme. All'08/09 alle 15:40 l'albero è
  **pulito**: i tre orfani di stamattina (`.claude/agents/code-reviewer.md`,
  `.claude/settings.json`, `tests/test_audit_fase6_rientro_bypass.py`) erano
  **completi, solo non committati**, e sono entrati in `24b0ae0`. Se ne trovi
  di nuovi: contali, non committarli, non scartarli.
- **Push e deploy: chiedi a Mattia.** Railway ridispiega anche per soli `.md`;
  Vercel solo su `apps/web/**`. Un commit locale non deploya niente.
- **Il marker del gate di review è condiviso fra sessioni**
  (`.claude/.reviewer_gate_ok` non ha il session id nel nome). Se `git status`
  mostra lavoro altrui su path sensibili, **non scriverlo**: il tuo Stop passa
  comunque grazie al marker anti-loop per-sessione, e l'altra sessione deve
  fare la sua review. E dopo aver chiuso i blocchi di una review, **ri-lancia
  la review sul cumulativo** prima di scriverlo: l'08/09 il Punto 2 è stato
  dichiarato chiuso con i fix mai ri-revisionati.
- **Se un'altra sessione sta scrivendo nello stesso albero**, leggi da
  `git show HEAD:<path>`, non dal disco; e per suite e mutanti usa una copia
  (`git worktree add --detach <dir> HEAD`), così il tuo mutante non finisce
  nella sua suite e il suo file a metà non finisce nella tua.
- **PostgREST tronca a 1000 righe senza errore**: ogni select che precede una
  scrittura passa da `fetch_all` (`utils/supabase_paging.py`).
- **`comm` vuole input ordinato** e i grep sugli scrittori devono escludere
  `sys.path.insert`, `dict.update`, `list.insert`: sono i tre modi con cui i
  conteggi precedenti sono usciti sbagliati.

## Chiusura (WORKFLOW.md §5)

Presidio provato per mutazione · commit su `main` locale · verbale nel
documento vivo con «17 di cui N provate» e i nomi · `check_documentazione.py`
pulito · `/code-reviewer` **verde sul cumulativo** · Mattia avvisato di
**quando cambiare modello** (chiusa la Parte A, prima della B).

Chiusa la Parte B, **il DB entra nel contatore**: nel documento vivo la riga
«Logica SQL dentro il DB» passa da «mai eseguita da un test» a «75 funzioni,
N eseguite, 35 di servizio escluse con motivo». È la quarta riga che al 97%
mancava.
