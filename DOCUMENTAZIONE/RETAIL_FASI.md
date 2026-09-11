# Retail — le fasi dell'implementazione

Stato all'**11/09/2026, sera**: **IMPLEMENTAZIONE CHIUSA E IN PRODUZIONE** — Fasi
0-5 e Chiusura. Il branch `retail` e' stato riportato su **`main` con rebase**
(fast-forward, nessun merge commit), branch e worktree rimossi, le **due migration
applicate sul DB**, e il tutto **pushato l'11/9 alle 20:14 UTC** (`283dcf2..2dbc77d`,
deciso da Mattia). Punto di ritorno: tag `pre-deploy-retail-20260911` (= `283dcf2`).

> **Il numero di commit non sta scritto qui**, di proposito: una cifra in un file
> versionato non puo' contare i commit che la aggiornano, e le prime due stesure
> di questa riga erano infatti sbagliate in due modi diversi. Finche' il lavoro non
> e' pushato si legge con `git log --oneline origin/main..main | wc -l`, che conta
> pero' **anche i commit delle altre sessioni**: si guarda chi li ha fatti prima di
> attribuirseli. Dopo il push la cifra si legge da `git log 283dcf2..2dbc77d`.
Fase 0 `b642e3c` · Fase 1 `50fc209` (sette buchi della stessa famiglia trovati dal
reviewer in sei letture, tutti chiusi) · Fase 2 `a7075f9` + residuo `e90ac30`
(11 mutanti) · **Fase 3** `5d9f367`, `c7e0d3b`, `dd6ac5e`, `c693a17`, `81d65a5`,
`5c98761`, `77b9e7c` (56 presidi, 17 mutanti, reviewer verde due volte).
**Fase 4** `23c0706`, `f76ddf1`, `ec43fc2`, `a6bb45d`, `e91f576`, `d4867c0`
(+ `a4166e4`, `2aec741` verbale): **241 presidi, 43 mutanti, 7 presidi finti**
smascherati dalla mutazione, reviewer 🔴 **tre volte** e poi chiuso.
**Fase 5** (sorveglianza post-deploy) **CHIUSA** 11/9/2026: 18 mutanti, 2 presidi
finti smascherati (stesso errore due volte: un assert sul sorgente invece che sul
comportamento), 2 difetti veri trovati dai presidi, reviewer 🟢 **due volte**.
**Chiusura finale fatta e deployata l'11/9 sera.** Misurato 20 minuti dopo il push:
CI tutta verde (compresa la suite, che vedeva il codice per la prima volta), worker
su `2dbc77d`, Vercel READY, monitor `200` con `totale: 0`, zero scritture sui dati
dei clienti dal push, baseline «Diff a zero» di nuovo. Reviewer 🟢 sul cumulativo
dei 50 commit (7 mutanti su call-site condivisi, tutti uccisi).

> ## ⛔ PRIMA DEL PUSH — la lista che NON si ricostruisce a memoria
>
> Mattia **non applica niente a mano**: ogni passo qui sotto lo esegue la sessione
> che porta il retail al deploy, e glielo si fa approvare passo per passo. Se stai
> leggendo questo file in una sessione nuova, **questa lista è il contratto**: non
> si pusha finché non è tutta spuntata, e non si spunta niente "da quello che
> ricordo" — si misura.
>
> 1. **✅ FATTO l'11/9/2026 sera — DUE migration APPLICATE sul DB vivo**, in
>    quest'ordine: **`20260910163000_add_tipo_attivita.sql`** e
>    **`20260911170000_v_categorie_settore_incoerenti.sql`** (la view del monitor:
>    senza, l'endpoint di sorveglianza risponde 500).
>    Va applicata sul DB **prima** del push (Railway ridispiega a ogni commit, anche
>    per soli `.md`, e il codice nuovo leggerebbe una colonna inesistente).
>    Si ri-verifica con `git diff main --name-only -- supabase/migrations/`.
>    Contiene due cose, non una: la colonna `ristoranti.tipo_attivita` **e** il
>    `CREATE OR REPLACE` di `assegna_fattura_a_sede_tecnica` (la sede tecnica deve
>    ereditare il settore, o su un account retail nascerebbe 'ristorazione').
> 2. **✅ Misurato prima di applicare** (11/9): colonna assente, constraint assente,
>    view assente, `assegna_fattura_a_sede_tecnica` presente ma **nella versione
>    vecchia** (`position('tipo_attivita' in prosrc)` = 0). Erano davvero pendenti.
>    Dopo: colonna 1, constraint 1, funzione che cita il settore, view con
>    `reloptions = {security_invoker=true}` e **0 righe incoerenti** sui dati veri.
> 3. **✅ Misurato dopo**: **12 sedi su 12 a `'ristorazione'`** (1 delle quali tecnica),
>    nessuna a `'retail'`. Il default ha coperto tutto l'esistente.
> 4. **✅ Baseline «Diff a zero» DUE volte DOPO le migration**, in processi nuovi
>    (56 righe di costi, 3.475 categorie invariate) + `retail_backup.py --verify`
>    allineato. I numeri dei ristoranti non si sono mossi di un centesimo.
> 5. **✅ Rebase su `main` e ri-esegui tutto** (suite, `-m sql`, tsc, OpenAPI,
>    `check_documentazione`): fra l'ultima fase e il deploy `main` sarà avanzato.
>    Se il rebase porta dentro modifiche a `ai_service.py`, `margine_service.py` o a
>    funzioni SQL, **la baseline si ri-cattura**: fotografa il codice, non solo i dati.
> 6. **✅ `/code-reviewer` sul cumulativo completo**, non sull'ultima fase (verde
>    prima del push e di nuovo dopo, sui 50 commit in produzione).
> 7. **`_BRIEFING_CODE_VERSION`: ✅ GIA' FATTO** — bumpata 23 → **24** dalla Fase 4
>    (`ec43fc2`), che tocca la logica del briefing: per un negozio l'anomalia
>    coperti non viene piu' generata. Non va toccata di nuovo prima del push.
> 8. **✅ Il push lo ha deciso Mattia** l'11/9 alle 20:14 UTC: 50 commit, tutti
>    retail tranne 1 GDPR di un'altra sessione. Mai `git push` di iniziativa.
>
> Il rollback sta in «Tornare indietro», in fondo a questo file. Prima del push il
> costo è zero: il branch non esiste per nessuno.

**Questo è il documento unico dell'implementazione**: contesto, decisioni, fatti misurati,
fasi con checklist, gate, deploy, rollback. Il piano di plan-mode
(`~/.claude/plans/mi-piacerebbe-che-l-app-curious-milner.md`) è **superato** da questo
file. Lo stato per riprendere la sessione stava in `docs/piani/PIANO_RETAIL.md`
(locale, git-ignorato), **eliminato alla Chiusura dell'11/9/2026**: il lavoro e' finito
e due fonti sullo stesso stato sono un rischio, non una comodita' (`WORKFLOW.md` §2).

> Si aggiorna **durante** il lavoro, non alla fine: le caselle si spuntano quando il gate
> di fase è passato, non quando il codice è scritto. Il nome del file non è casuale: il
> repo ignora `*IMPLEMENTAZIONE*.md` (`.gitignore:79`).

---

## ~~Come si riprende~~ — non c'e' piu' niente da riprendere

> **Dall'11/09/2026 (Chiusura) non c'e' piu' niente da eseguire qui.** Il branch `retail` e il worktree
> `/home/vscode/ONEFLUX-retail` **non esistono piu'**: il lavoro sta su `main` in
> `/workspaces/ONEFLUX` e le due migration sono applicate. Questo blocco resta come
> traccia di come si e' lavorato, non come istruzioni da eseguire — i comandi qui
> sotto oggi fallirebbero. Se serve rimettere le mani sul retail, si parte da `main`.

```
cd /home/vscode/ONEFLUX-retail             # (non esiste piu')
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

**Dove si lavorava** (fino alla Chiusura dell'11/9, poi rientrato su `main`):
branch `retail` nel worktree `/home/vscode/ONEFLUX-retail`.
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

**Aggiornamento 10/9 sera**: il fatto non spiegato È spiegato — vedi «Trovato durante la
1.1». Due check verdi di fila (16:20) non erano una prova: la lettura sbagliata capita
~2 volte su 10.

---

## Fase 1 — Isolamento · **bloccante per tutte le altre** · Fable, ultrathink · **CHIUSA** 11/9/2026 (`50fc209`)

Nessuna fase successiva parte prima che questa abbia passato il gate. Sottofasi
nell'ordine: ogni casella si spunta col gate 4-5 (baseline) rifatto.

### 1.1 Migration e perno

**Chiusa il 10/9 sera** (commit `eb8818c` dopo il rebase; gate 4-5 passato con due check a
zero dopo il fix `da269ad` su `main`). Fatto e misurato: migration
`20260910163000_add_tipo_attivita.sql` (si scrive, non si applica; il harness `-m sql` la
applica sopra lo snapshot: **180 verdi**, erano 176 prima — il «164» di questo documento
era una cifra ereditata); `_SEDE_SELECT` con `tipo_attivita` e usato anche da
`admin_dettaglio_cliente` (aveva la stessa lista copiata a mano); body con `pattern` come
`piano`; `_settore_sede_coerente` in `routers/admin.py` (vincolo di omogeneità, sede
tecnica esclusa, la sede stessa esclusa in modifica, 400 senza scrivere); `UserPublic`
con `Literal` e default; `SessionUser`/`Sede`/form admin (select «Settore», bloccato
quando l'account ha già sedi; badge solo se retail). Costanti `SETTORE_*` in
`config/constants.py`. Test nuovi: `tests/test_retail_sede_tipo_attivita.py` (21) e
`tests/test_sql_retail_tipo_attivita.py` (4). **11 mutanti su 11 uccisi**, uno per volta,
`.bak` preso prima, ognuno dal test che doveva ucciderlo. `tsc --noEmit` pulito, OpenAPI
riesportato senza drift, suite **13.385 verdi** (+25). Decisione presa (da confermare):
con più sedi il settore **non si cambia** dal pannello — un account retail nasce tale
dalla prima sede; sbloccarlo richiederebbe di propagare a tutte le sedi, rimandato.

- [x] `supabase/migrations/AAAAMMGGHHMMSS_add_tipo_attivita.sql`:
      `ALTER TABLE ristoranti ADD COLUMN tipo_attivita TEXT NOT NULL DEFAULT 'ristorazione'`
      + `CHECK (tipo_attivita IN ('ristorazione','retail'))`. **Si scrive, non si applica.**
- [x] **Ereditarietà della sede tecnica**: l'INSERT dentro `assegna_fattura_a_sede_tecnica`
      (`supabase/schema_snapshot.sql:1614-1621`) elenca 6 colonne e non include
      `tipo_attivita` → su un account retail la sede tecnica nascerebbe `'ristorazione'`.
      Copiare il valore dalla stessa sede reale da cui già copia la P.IVA. Anche questa è
      SQL nella stessa migration (`CREATE OR REPLACE`), stessa firma
- [x] `_SEDE_SELECT` (`services/routers/admin.py`), `NuovaSedeBody` /
      `ModificaSedeBody` (`:2933-2953`, pattern come `piano`), `admin_crea_sede` (`:2966`,
      insert a `:2991`), `admin_modifica_sede`
- [x] **Vincolo di omogeneità** in `admin_crea_sede`, con `.eq("sede_tecnica", False)`:
      la sede tecnica è esclusa dal vincolo (coerente coi 15+ punti che già la escludono)
- [x] `UserPublic` (`services/fastapi_worker.py:1176`) e `SessionUser`
      (`apps/web/src/lib/auth.ts:19`), campo additivo col default
- [x] Frontend admin: form sede in `cliente-dettaglio-client.tsx`, tipo `Sede` in
      `apps/web/src/lib/admin.ts:3`

### Trovato durante la 1.1: la memoria locale si carica a metà (paginazione senza ORDER BY)

Il `check` dopo la 1.1 divergeva — 6 righe di LAND DEI SAPORI, poi 7 di San Giuliano,
poi 7 di Villa Guardia, **una sede per esecuzione, sempre verso `Da Classificare`**, con
un salto vero (`CONTRIBUTO SPESE DI CONSEGNA`: `SERVIZI E CONSULENZE` → `GELATI E
DESSERT`). La 1.1 non tocca `ai_service`, i contatori del DB erano invariati e le stesse
righe in isolamento uscivano giuste 3 volte su 3.

Misurato, non dedotto (10/9 sera, sola lettura):

- **tutte e 14 le righe divergenti sono `L2_locale`** (`ultima_provenienza()`), e
  svuotando in-process la sola memoria locale si ottiene *esattamente* l'output
  divergente, salto a GELATI compreso (regola fornitore L5 che prende il posto della
  memoria);
- le tre sedi sono **lo stesso utente** (`51015cc8`, SUSHILAND): l'unico con più di
  mille voci in `prodotti_utente` (**3.067 = 4 pagine**; gli altri: 779, 658, 639, 217, 24);
- `ai_service._fetch_all_rows` pagina con `range()` **senza ORDER BY**. Su 10 letture
  consecutive di quell'utente: **8 complete, 2 con buchi — 66 e 653 id mancanti su
  3.067**, sostituiti da duplicati, **con il totale sempre 3.067**. Nessuna scrittura in
  corso (ultimo `updated_at` 27/8): è il planner che cambia ordine fisico fra una pagina
  e l'altra della stessa lettura;
- la Fase 0 aveva «provato» la paginazione contando le righe (3.067 su 20 esecuzioni):
  un aggregato che torna con errori che si compensano. Le 6 ipotesi scartate e le 24
  divergenze delle 10:58 sono spiegate da questo.

**Effetto in produzione, oggi, per un cliente ristorazione**: il worker carica la memoria
locale di SUSHILAND a metà in ~2 letture su 10, la tiene in cache per **1 ora**
(`_CACHE_TTL_SECONDS`), e in quell'ora le correzioni del cliente sulle voci mancanti non
valgono: le righe finiscono all'AI, al dizionario o alla regola fornitore. Stessa classe
su `prodotti_master` (2.913 righe = 3 pagine, memoria globale di **tutti** i clienti).
`_fetch_all_rows` ha 4 chiamanti, tutti in `ai_service.py` (`:3092`, `:3126`, `:3172`,
`:4542`). Fix candidato: un `.order("id")` dentro `_fetch_all_rows`, più un test che
confronti gli **id distinti** e non il conteggio. `utils/supabase_paging.fetch_all` ha lo
stesso rischio per i chiamanti senza `.order()` (l'esempio nel suo docstring non lo ha).

**Non è retail e non è in questo piano**: cambia il comportamento per i ristoranti (in
meglio), quindi lo ha deciso Mattia: **su `main`, commit `da269ad`** (10/9 sera), col push di
stasera. `.order("id")` in `_fetch_all_rows`, test provato con tre mutanti (senza ordine,
per descrizione, decrescente), due fake di test esistenti hanno imparato `.order()` (col suo
ok). Dopo il fix: 10 letture su 10 complete. Il reviewer ha misurato il costo (~2 ms in più
sull'ultima pagina, index scan sulla PK) e contato **33 chiamanti di `fetch_all` senza
`.order()` su 34** — stessa classe, superficie 13× su `fatture`: decisione separata.

**Effetto collaterale del fix, dichiarato**: nella mappa normalizzata della memoria locale
(`prodotti_utente_norm`) più voci possono collidere sulla stessa chiave (le 6 «PER CONSUMO
FUSTI BIRRA MORETTI MESE …» di SUSHILAND normalizzano tutte a «PER CONSUMO FUSTI BIRRA
MORETTI»: 1 manuale SERVIZI, 4 automatiche BIRRE) e **vince l'ultima caricata**. Prima
l'ordine era quello fisico (≈ la più recente); ora è per `id` (uuid: deterministico ma
arbitrario). Sulla baseline cambia **1 riga su 3.475** (Villa Guardia, GIUGNO: BIRRE →
SERVIZI E CONSULENZE, verso la correzione manuale) — ma la baseline campiona: ri-misurato
sulla memoria intera l'11/9 (review dei commit di `main`), cambiano **39 chiavi su 5.206**, e
sul cliente da 3.067 voci in **5 gruppi su 28 è la correzione manuale a perdere** contro
un'automatica. La direzione non è «verso il manuale»: è arbitraria (uuid), prima arbitraria
*e* instabile, ora arbitraria e ferma. La baseline è stata
**ri-catturata** su `main` + fix (la baseline fotografa il codice) e il check è a zero due
volte. **Domanda di design per Mattia, non urgente**: sulle collisioni dovrebbe vincere per
regola la voce manuale sulle automatiche (e la più recente a parità), non l'ordine di
lettura. Oggi non lo fa in nessuna delle due versioni.

### 1.2 `services/settore_service.py` (nuovo)

Modulo separato: `ai_service.py` è già importato da mezzo mondo, e la funzione serve anche
a router che non fanno AI.

**Chiusa il 10/9 sera** (commit `4743b2a` dopo il rebase; stesso gate della 1.1).
`settore_utente` / `settore_sede` /
`is_retail` / `invalida_cache`, cache con lock e TTL 300 s, errore DB **non** messo in cache,
valore sconosciuto → ristorazione. Cablato in `/api/auth/login` e `/api/auth/me`
(`UserPublic.tipo_attivita`, che prima restava al default) e nell'admin: crea, modifica del
settore ed elimina sede invalidano la cache dell'account. Test nuovi:
`tests/test_settore_service.py` (14), `tests/test_auth_settore_wiring.py` (3), +4 in
`tests/test_retail_sede_tipo_attivita.py`. **11 mutanti su 11 uccisi.** «Risolto una volta
per documento» si spunta in 1.3, dove il settore entra nella classificazione.

- [x] `settore_utente(user_id)` e `settore_sede(ristorante_id)`
- [x] Cache modulo-level con `threading.Lock` + TTL **300s** (pattern di `_memoria_cache`,
      `ai_service.py:290-291`; TTL corto: il settore cambia solo per mano dell'admin)
- [x] Query: `user_id = ? and attivo = true and sede_tecnica = false limit 1`
- [x] **Utente senza sedi → `'ristorazione'`** (caso reale: `auth_service.py:517-520`
      crea account senza sedi se manca la P.IVA). Fail-safe nella direzione giusta
- [x] Risolto **una volta per documento**, fuori dal loop righe
- [x] **Mai** negli header del client Supabase: è un singleton condiviso, i suoi header
      sono stato globale e hanno già rotto la produzione. Il dato viaggia come argomento

### 1.3 Filtro d'uscita nella classificazione

`categorizza_con_memoria` (`services/ai_service.py:4905-5182`) **non chiama mai l'AI**:
finisce sul dizionario. Il canale per mandare una riga all'AI esiste già ed è restituire
`Da Classificare` con `is_fallback=True` — i chiamanti lo interpretano come "passala
all'AI e marca `needs_review`" (`services/invoice_service.py:1157-1170`).

- [x] Gate dentro la closure `_ret` (`:4952-4980`): **tutti i 12 return passano di lì**,
      nessun early-return la salta. Se retail e la categoria è in `CATEGORIE_FOOD_BEVERAGE`
      → `Da Classificare` + `is_fallback=True`, provenienza `"nessuna"`
- [x] **Non filtrare** i livelli generici, corretti anche per un negozio: L0 fornitore
      utility → UTENZE, L4 dicitura → NOTE (gate `prezzo == 0`), L6 unità di misura,
      guardrail. Il gate guarda **solo** l'appartenenza alle food
- [x] Seconda guardia sull'auto-save locale (`:5124`): riceve `categoria_keyword`, non il
      ritorno di `_ret` — il filtro da solo non lo blocca

**Chiusa il 10/9 sera.** `categorizza_con_memoria(..., settore=None)`: kwarg in coda, i
chiamanti di oggi non lo passano e il percorso resta letteralmente quello di prima
(provato: con `None` e `'ristorazione'` output e provenienza identici). Il gate sta in
`_ret` (da cui passano tutti i return) e restituisce `Da Classificare` con
`is_fallback=True` e provenienza `nessuna`; la seconda guardia azzera `categoria_keyword`
prima dell'auto-save. L'unico chiamante di produzione è `estrai_dati_da_xml`
(`invoice_service.py`), che risolve `settore_utente(user_id)` **una volta per documento**
e lo passa come argomento; senza `user_id` e senza `settore` esplicito resta `None` —
l'anteprima coda lo passa esplicitamente (vedi «Sesta lettura»). Test:
`tests/test_retail_filtro_uscita_classificazione.py` (11) e
`tests/test_retail_settore_per_documento.py` (3, sul parser vero con XML sintetico).
**7 mutanti su 7 uccisi** su base verde (gate spento, seconda guardia spenta, gate solo
CARNE, gate rovesciato sui ristoranti, gate senza fallback, parser che non passa o non
risolve il settore). Check baseline a zero prima e dopo la mutazione.

### 1.4 Post-AI: quattro punti che riporterebbero in food

- [x] **`:5412` — bloccante**: `if cat not in TUTTE_LE_CATEGORIE` sostituisce la categoria
      con `decisione_deterministica(desc)`. Senza questo, il prompt retail (Fase 2) **non
      produce nulla**, qualunque cosa risponda GPT, e il sintomo sarebbe indistinguibile
      da "il prompt non funziona". Whitelist di validazione funzione del settore —
      **mai** aggiungere `ARTICOLO DI VENDITA` a `TUTTE_LE_CATEGORIE`
- [x] `:5629` safety net (`decisione_deterministica` sui `Da Classificare`): saltare se retail
- [x] `:5676` override post-AI (`applica_regole_categoria_forti`): saltare se retail
- [x] `worker/queue_processor.py:487` `_categoria_deterministica_runtime`: scavalca la
      proposta AI quando il dizionario è certo. Saltare se retail

**Chiusa il 10/9 sera.** `categorie_ammesse(settore)` in `settore_service` (ristorazione →
`TUTTE_LE_CATEGORIE` identica; retail → `ARTICOLO DI VENDITA` + 4 spese generali; la costante
`CATEGORIA_ARTICOLO_DI_VENDITA` sta in `config/constants.py` **fuori** da ogni lista
condivisa). `_chiama_gpt_classificazione` e `classifica_con_ai` prendono `settore=None` in
coda; la validazione usa la whitelist del settore e per il retail **non** recupera dal
dizionario (resta `Da Classificare`); safety net e override post-AI spenti per il retail,
anche nei retry. Il settore si risolve dall'`user_id` in **`/api/classify`** (il body lo ha
già: contratto HTTP invariato, OpenAPI senza drift), nel fallback locale di
`worker_client` e una volta per file in `_auto_classify_saved_rows`, dove l'override
deterministico resta spento. Fuori scope dichiarato: `prepara_suggerimenti_ai` (admin)
lavora su `prodotti_master`, che la 1.5 tiene solo-ristorazione. Test:
`tests/test_retail_post_ai.py` (16, sul classificatore vero con un client OpenAI finto,
sull'endpoint vero e sull'harness esistente del worker). **9 mutanti su 9 uccisi** — uno
(il retry che perde il settore) è sopravvissuto al primo giro perché il test faceva
rispondere «Da Classificare» anche ai retry: aggiunto il caso in cui il retry propone una
food. Check baseline a zero due volte.

### 1.5 Memoria globale — 2 scritture, 3 letture

- [x] Scrittura `aggiorna_streak_classificazione` (`:3240`): guardia **nel chiamante**
      (`worker/queue_processor.py:543`, che ha `user_id` in scope). Firma invariata
- [x] Scrittura `salva_correzione_in_memoria_globale` (`:4673`), via `routers/admin.py:1657`
- [x] Lettura L3 dentro `categorizza_con_memoria` (`:5068`, `:5080`) — già coperta da `_ret`
- [x] Lettura `ottieni_categoria_prodotto` (`:3740`, chiamata da `invoice_service.py:1700`,
      percorso PDF/Vision) — **funzione diversa**, legge in proprio: guardia separata.
      (Il piano la chiamava `suggerisci_categoria_da_memoria`: nome mai esistito, ri-misurato)
- [x] Lettura `ottieni_hint_per_ai` (`:3544`, chiamata da `upload_handler.py:661`) — inietta
      un hint nel **prompt GPT** ("CARNE" su una riga di ferramenta): sfugge a qualunque
      filtro d'uscita. (Il piano la chiamava `_hint_da_memoria_globale`: idem)

**Chiusa il 10/9 sera.** Scritture: nel worker lo streak parte solo se `_settore !=
retail` (la riga si scrive lo stesso); la promozione admin (`admin_qualita_risolvi_conflitto`,
azione `promuovi`) legge anche `user_id` dalla voce locale e risponde **400** se l'account è
retail. Letture: `ottieni_categoria_prodotto(..., settore=None)` ha lo stesso gate di `_ret`
dentro `_ret_ocp`; `ottieni_hint_per_ai(..., settore=None)` restituisce `None` per il retail;
L3 era già coperta dal gate della 1.3. Cablaggio: `_run_post_upload_ai_categorization`
risolve il settore una volta per lotto e lo passa agli hint; `estrai_dati_da_scontrino_vision`
una volta per documento. Test: `tests/test_retail_memoria_globale.py` (10, riusando gli
harness esistenti del worker, del pannello admin e del Vision). **7 mutanti su 7 uccisi.**
Check baseline a zero due volte.

### 1.6 Propagazione storica — il difetto più grave, esiste già oggi

`_propaga_global_override_a_fatture_storiche` (`services/ai_service.py:4581-4590`): la
query su `fatture` filtra per `deleted_at` e per token della descrizione, **senza alcun
filtro su `user_id` o `ristorante_id`**. Fa UPDATE reali. Un admin che corregge una
descrizione comune riscrive la categoria sulle fatture storiche di **tutti i clienti**.
Non è un problema retail: è un fix per i clienti attuali, e va **detto a Mattia** quando
si chiude.

- [x] Filtro tenant **dentro** la funzione (ha due chiamanti: `admin.py:1541` e `:1657`)
- [x] Test per mutazione: correzione su un cliente → zero UPDATE sulle fatture di altri

**Chiusa il 10/9 sera — con una precisazione che spetta a Mattia.** Il filtro è per
**settore** del tenant, dentro la funzione (tre chiamanti: `admin.py` e le due promozioni in
`salva_correzione_in_memoria_globale`): le fatture di un account retail non vengono
riscritte da una correzione della memoria globale, che è dei ristoranti. **Non** ho
limitato la propagazione al solo cliente della correzione, come la frase «zero UPDATE sulle
fatture di altri» poteva far pensare: il docstring della funzione e il test esistente
`tests/test_propagazione_globale_guardrail_note.py` (due utenti, entrambi raggiunti)
dichiarano il raggio cross-cliente fra ristoranti come comportamento **voluto** — è la
promozione admin alla memoria globale, «per tutti». Cambiarlo sarebbe una modifica ai
ristoranti (violerebbe il vincolo) e una decisione di prodotto: se Mattia la vuole, è un
lavoro a sé. Test: `tests/test_retail_propagazione_tenant.py` (3). **2 mutanti su 2
uccisi.** Nota nella stessa funzione: la paginazione delle `fatture` candidate usa
`range()` senza `ORDER BY` (stessa classe di `da269ad`): non toccata, sta nell'elenco dei
33 chiamanti da decidere.

### 1.7 Dropdown categorie

`services/routers/fatture.py:820-855` unisce `categorie_usate` (già filtrate per
`ristorante_id`) alle **canoniche non filtrate**.

- [x] Non inserire `ARTICOLO DI VENDITA` nella tabella `categorie` (è globale: comparirebbe
      nel menu di ogni ristorante). Compare da sola via `categorie_usate` appena esiste una riga
- [x] Filtrare le canoniche per settore

**Chiusa il 10/9 sera.** Per un account retail le canoniche diventano
`categorie_ammesse('retail')` (ARTICOLO DI VENDITA + spese generali); le usate della sede
restano; per i ristoranti l'unione è quella di oggi. Test:
`tests/test_retail_dropdown_categorie.py` (4). **3 mutanti su 3 uccisi.** Check baseline a
zero due volte dopo 1.6+1.7.

---

### Inerenze della Fase 1 — chi chiama cosa (gate 8)

Ogni simbolo toccato, coi chiamanti misurati col grep **prima** della modifica. Le firme
sono tutte **additive** (kwarg in coda con default `None`): chi non passa il settore ottiene
il comportamento di prima.

| Simbolo toccato | Chiamanti (misurati) | Esito |
|---|---|---|
| `ristoranti.tipo_attivita` (colonna) | `_SEDE_SELECT` ×2, `admin_dettaglio_cliente` (ora usa `_SEDE_SELECT`), `assegna_fattura_a_sede_tecnica` (SQL), frontend `Sede` | tutti aggiornati |
| `categorizza_con_memoria(settore=)` | `invoice_service.estrai_dati_da_xml` (unico in produzione), `scripts/retail_baseline.py` (non passa: baseline = ristorazione) | 1 cablato, 1 volutamente no |
| `classifica_con_ai(settore=)` | `fastapi_worker.classify` (cablato), `worker_client` fallback locale (cablato), `admin.prepara_suggerimenti_ai` (fuori scope: `prodotti_master` è solo-ristorazione per la 1.5) | 2 cablati, 1 dichiarato |
| `_chiama_gpt_classificazione(settore=)` | solo `classifica_con_ai` (prima chiamata + retry) | entrambe |
| `ottieni_categoria_prodotto(settore=)` | `invoice_service.estrai_dati_da_scontrino_vision` | cablato |
| `ottieni_hint_per_ai(settore=)` | `upload_handler._run_post_upload_ai_categorization` | cablato |
| `_propaga_global_override_a_fatture_storiche` (filtro interno) | `admin.py` (memoria update), `salva_correzione_in_memoria_globale` ×2 | filtro nel corpo: vale per tutti |
| `aggiorna_streak_classificazione` | `worker/queue_processor.py` (guardia nel chiamante) | firma invariata |
| `salva_correzione_in_memoria_globale` | `admin_qualita_risolvi_conflitto` (guardia nel chiamante) | firma invariata |
| `get_categorie_disponibili` | frontend (`/api/fatture/categorie`) | contratto invariato |
| `get_prompt_classificazione(settore=)` (Fase 2) | 1 solo consumatore vivo: `ai_service._chiama_gpt_classificazione:5393` (cablato). `scripts/ab_test_modello_categorizzazione.py:76` non passa il settore → ristorazione, voluto | 1 cablato, 1 dichiarato |
| `UserPublic` / `ClassifyRequest` | OpenAPI riesportato: nessun drift | — |
| `_fetch_all_rows` (main, `da269ad`) | 4 chiamanti, tutti in `ai_service` | ordinati per `id` |
| **`decisione_deterministica`** (il dizionario dei ristoranti: la vera superficie d'uscita, mancava in questa tabella — segnalato dal reviewer) | 12 chiamanti: `queue_processor:180` (override guardato in 1.4; la conferma può solo confermare categorie generiche), `upload_handler:62` e `:801` (conferma ed etichetta di fonte: idem), `ai_service:3889` (`_ret_ocp`), `:5474` (validazione per settore), `:5700` (safety net spento), **`:5575`/`:5783`/`:5797` (i tre rami degradati: erano SCOPERTI)**, **`fastapi_worker:397` (agente notturno: era SCOPERTO)**, `admin.py:820` (**era dichiarato «nessuna scrittura», falso**: il suggerimento arriva al bulk «Accetta tutti» — terzo buco, chiuso sotto), `:1171` (`prepara_suggerimenti_ai`, scrive solo `prodotti_master.categoria_suggerita`, fuori scope dichiarato), `:1454` (elenco «sospette», sola lettura) | 3 buchi chiusi (sotto), 9 coperti o dichiarati |

### Seconda lettura (code-reviewer, 10/9 sera): due buchi veri, chiusi

Il reviewer ha **eseguito** il codice, non letto: `classifica_con_ai(["BISTECCA DI MANZO",
"VINO ROSSO", "TROTA SALMONATA"], settore="retail")` con OpenAI assente restituiva
`['CARNE', 'VINI', 'PESCE']`. Due punti d'uscita food fuori dal gate, entrambi passavano dal
dizionario dei ristoranti senza guardare il settore:

1. **I tre rami degradati di `classifica_con_ai`** (client OpenAI assente, JSON rotto,
   errore generico): decidevano col dizionario. Non è un caso raro — il worker riconosce il
   degrado (`_ai_muta`) ma **scrive comunque** quelle categorie. Ora per il retail restano
   `Da Classificare` (regola #1); per i ristoranti invariato. Il sorgente conserva le tre
   chiamate letterali a `decisione_deterministica(desc)`: un test esistente
   (`test_classifica_con_ai_non_ricompone_la_pipeline`) ne conta la presenza.
2. **L'agente notturno** (`_run_agent_notturno`) riclassificava la coda di **tutti** gli
   utenti non-admin col dizionario e promuoveva la descrizione in `prodotti_master`
   `verified=True`: per un negozio righe riscritte in CARNE/VINI **e** memoria globale dei
   ristoranti contaminata. Ora gli account retail sono esclusi **prima** della query sulle
   fatture: ciò che non viene letto non può essere scritto. Le loro righe in coda aspettano
   l'AI col prompt del settore (Fase 2).

Test: +3 in `tests/test_retail_post_ai.py` (i tre rami, eseguiti come ha fatto il reviewer)
e `tests/test_retail_agente_notturno.py` (3). **4 mutanti su 4 uccisi** (i tre rami uno per
volta, il filtro dell'agente). Check baseline a zero due volte.

3. **La coda qualità dell'admin** (terza lettura del reviewer): avevo classificato
   `_suggerimento_deterministico` come «suggerimento mostrato all'admin, nessuna
   scrittura». Falso: `admin_qualita_coda` lavora su tutti gli utenti non-admin, il
   frontend (`admin/categorie/categorie-client.tsx`, «Accetta tutti») scrive in blocco
   proprio le fonti `regola`/`memoria`, e `admin_qualita_classifica` promuove poi la
   descrizione in `prodotti_master` `verified=True`. Delle due strade possibili (escludere i
   negozi dalla coda, o tenerli senza suggerimento) ho scelto la **seconda**, coerente con la
   guardia già scritta in `admin_qualita_risolvi_conflitto`: l'admin deve poter classificare
   a mano le righe di un negozio (finché la Fase 2 non porta il prompt retail, è l'unica via),
   quindi un gruppo che contiene righe retail **resta in coda senza suggerimento** (né
   deterministico né AI: «Accetta tutti» non lo raccoglie), e `admin_qualita_classifica`
   **non promuove** in memoria globale quando le righe sono tutte di account retail (un
   gruppo misto promuove per i ristoranti, come oggi). **Decisione da confermare con Mattia.**
   Resta per la Fase 3: la whitelist di `admin_qualita_classifica` è `TUTTE_LE_CATEGORIE`,
   quindi l'admin non può ancora scrivere ARTICOLO DI VENDITA (checklist «sei whitelist»).
   Test: `tests/test_retail_coda_admin.py` (6, sull'endpoint vero con gli harness esistenti).
   **3 mutanti su 3 uccisi.** Check baseline a zero due volte.

### Terza lettura — fatta a mano: la review automatica si è interrotta

La terza passata del code-reviewer si è fermata per il **limite di sessione dell'API**
(reset alle 19:00 UTC), non per un rosso: non ha scritto niente e non ha lasciato processi.
Ho fatto io il punto che le avevo chiesto — **l'inventario di ogni scrittura su
`prodotti_master` e `prodotti_utente`** raggiungibile in produzione (grep a riga singola e
multi-riga, 20 punti) — e ne è uscito un quarto buco, della stessa famiglia del terzo:

| Punto di scrittura | Cosa scrive | Esito per un account retail |
|---|---|---|
| `ai_service.py:3334/3380/3385` (`aggiorna_streak_classificazione`) | master | guardato nel chiamante (1.5) |
| `ai_service.py:3726`, `:5193` (auto-save locale) | utente | categoria già gated (seconda guardia 1.3) |
| `ai_service.py:4483` (`salva_correzione_in_memoria_locale`) | utente | correzione del cliente stesso: locale, giusta |
| `ai_service.py:4765/4794` (`salva_correzione_in_memoria_globale`) | master | unico chiamante guardato (400, 1.5) |
| `upload_handler.py:903` (memoria AI post-upload) | utente | categoria da `classifica_via_worker`, gated (1.4) |
| `fastapi_worker.py:360/383/432` (agente notturno) | master | account retail esclusi prima della query (seconda lettura) |
| `admin.py:1084` (`admin_qualita_classifica`) | master | solo se almeno una riga ristorazione (seconda lettura) |
| `admin.py:1257` (`prepara_suggerimenti_ai`) | master, solo `categoria_suggerita` | chiamanti: agente notturno (retail esclusi) e **`admin_qualita_suggerisci_ai` (ora esclude i retail)** |
| **`admin.py:1379/1406` (`admin_qualita_auto_review`)** | master, `verified=True` | **era SCOPERTO**: per gli sconti/omaggi promuoveva la categoria già presente sulla riga — per un negozio ARTICOLO DI VENDITA — e da lì ai ristoranti come bypass. Ora le righe si classificano (una dicitura a importo zero è tale anche per un negozio, lo sconto conferma la categoria che la riga ha già) ma la promozione avviene solo se la descrizione ha almeno una riga ristorazione, come in `classifica` |
| `admin.py:1549/1581` (update/delete di una voce globale per id) | master | azioni dell'admin su voci già globali: neutre |
| `admin.py:1695` (marca «eccezione locale accettata») | utente | neutro |
| `db_service.py:1952` (cancellazione account) | utente | neutro |

Test: +5 in `tests/test_retail_coda_admin.py` (auto-review sugli endpoint veri, dicitura e
sconto di un negozio, gruppo misto; filtro dei suggerimenti). **2 mutanti su 2 uccisi** — il
test sugli sconti al primo giro passava **a vuoto**: il fake esistente non conosce
`.update()` e il ramo moriva nell'`except` prima della promozione; esteso il fake nel mio
file (non quello esistente) e il mutante ora è ucciso da entrambi i test. Check baseline a
zero due volte.

**Stato del gate 9**: due passate complete del reviewer (entrambe rosse, entrambe chiuse),
la terza interrotta dal limite API e sostituita da questo inventario, la quarta rifatta alle
21:40 sul cumulativo, la quinta alle 22:00 e la sesta alle 22:30, tutte rosse (vedi «Quarta»,
«Quinta» e «Sesta lettura»). Sui non bloccanti: il
verbale era più forte del vero (la riga qui sopra lo corregge); il `-16 righe` su
`AUDIT_COPERTURA.md` era la base non ancora rebasata su `main`, risolto col rebase;
`settore_sede`/`is_retail` senza chiamanti sono superficie per le fasi 3-4; l'N+1 latente
in `_propaga_global_override_a_fatture_storiche` (un `settore_utente` per riga candidata,
assorbito dalla cache 300 s) resta annotato.
### Quarta lettura (code-reviewer sul cumulativo, 10/9 ore 21:40): il quinto buco sta a valle di tutto

Il reviewer ha eseguito il codice, non letto: `classifica_con_ai(['CAFFE MISCELA BAR 1KG'],
lista_iva=[10], settore='retail')` con GPT che risponde MATERIALE DI CONSUMO usciva
**CAFFE E THE**. La causa: `_applica_guardrail_iva_bassa_spese_generali` («una spesa generale
con IVA 4/5/10 è sospetta: prova a recuperare una food dal dizionario») gira sul percorso di
successo **dopo** la validazione per settore, e sul livello L7 di `categorizza_con_memoria`
**prima** della seconda guardia, che avrebbe riportato la riga a «Da Classificare» invece di
lasciarle la spesa generale. Nessun test retail passava `lista_iva` con un valore basso, e
l'inventario della terza lettura guardava le scritture in memoria, non i passaggi a valle
dell'uscita. IVA 10 è un dato normale di fattura: era la norma, non un caso limite.

Fix: kwarg additivo `settore=None` nel guardrail (per un negozio ritorna la categoria
normalizzata, intatta: la premessa «IVA bassa ⇒ food» è da ristorante, la merce di un negozio
ha qualunque aliquota) e nel wrapper `_applica_tutti_guardrail`, passato dai 5 punti runtime
(`classifica_con_ai` ×4, L7 ×1). L'unico altro chiamante, `scripts/ricategorizza_sede.py`
(manuale, dry-run di default), non lo passa; `ricategorizza_sede_ai.py` non chiama il guardrail
ma replica il deterministico runtime e lo streak senza gate settore: entrambi residuo dichiarato
(residuo dichiarato a suo tempo), da chiudere prima che esista una sede retail. Test: +10 in `tests/test_retail_guardrail_iva.py` (guardrail da solo, wrapper,
percorso di successo con e senza confidenze, L7 con «SERVIZIO DI PRODUZIONE POLLO», che il
dizionario mette in SERVIZI e il guardrail portava in CARNE; ogni caso affiancato a `None` e
'ristorazione'). **5 mutanti su 5 uccisi** (gate spento, gate rovesciato, i tre punti runtime
senza `settore`); il sesto, su un percorso degradato, **sopravvive perché lì la categoria
retail è già «Da Classificare»** e il guardrail non ha su cosa agire: quel kwarg è
uniformità, non un presidio. Baseline a zero ×2 in processi nuovi; suite 13.487 verdi.

### Quinta lettura (code-reviewer sul cumulativo, 10/9 ore 22:00): il sesto buco è la mano dell'admin

Ancora eseguito, non dedotto: in `admin_qualita_classifica` il commit `64fbe5b` guardava solo
la promozione in `prodotti_master`, ma `aggiorna_categoria_fatture` riceveva **tutti** gli id
del gruppo. La coda raggruppa per descrizione su tutti i clienti (47 gruppi misti su 264, fino
a 5 sedi) e le righe dei negozi ci restano per scelta (1.5): l'admin sceglieva SALUMI per il
ristorante e la riga della ferramenta usciva SALUMI a DB. Il mio test sul gruppo misto
asseriva solo la memoria globale, con una spesa generale lecita anche per un negozio.

Fix: se la categoria scelta è food, gli id dei tenant retail escono dalla scrittura e restano in
coda (la risposta lo dice: `righe_in_coda`); se non resta nessuna riga, 422 come per NOTE a
importo diverso da zero; una spesa generale va su tutte le righe come prima. Test: +4 in
`tests/test_retail_coda_admin.py` (gruppo misto con food, negozio solo con food → 422, gruppo
misto con spesa generale, ristoranti soli con food come prima). **4 mutanti su 4 uccisi** (filtro
tolto, predicato rovesciato, settore rovesciato, 422 tolto). Suite 13.491 verdi.

Fuori dal blocco, dichiarato dal reviewer e lasciato alla Fase 3 (dove le sei whitelist di
scrittura sono già in elenco): le correzioni del cliente (`routers/fatture.py`,
`routers/riparto.py`) validano su `TUTTE_LE_CATEGORIE`, non per settore. Il menu è già filtrato
(1.7) e la memoria scritta è quella locale del tenant; una chiamata API diretta scriverebbe però
CARNE sulla riga di un negozio. La migration non è stata verificata sul DB vivo dal reviewer
(accesso MCP negato): lo stato applicato si misura su `information_schema` prima del push.

### Sesta lettura (code-reviewer sul cumulativo, 10/9 ore 22:30): il settimo buco è l'anteprima

Eseguito sulla catena vera: `estrai_dati_da_xml(xml, user_id=None)` + `costruisci_anteprima_righe`
dava SALUMI a «PROSCIUTTO CRUDO STAGIONATO». È l'anteprima della coda «da assegnare»
(`riparto_anteprima_coda`) e la sua gemella generata **all'ingresso** di ogni documento ambiguo
(`upload_invoice`, salvata in `fatture_queue.anteprima_righe`): entrambe passano `user_id=None`
di proposito — niente memoria, niente scritture — ma senza utente il parser non risolveva il
settore, e un negozio vedeva food sulla propria merce, in cache prima ancora di aprire la
schermata (sul DB vivo: 13 righe `da_assegnare` e 367 anteprime persistite su 3 account). Il
verbale della 1.3 registrava il fatto («senza `user_id` resta `None`») senza dirne la
conseguenza. Stesso schema dei sei precedenti: un `settore=None` arrivato per una ragione che
non c'entra col settore.

Fix: `settore` esplicito in `estrai_dati_da_xml` (vince su `user_id`; assente → si risolve da
`user_id` come prima), passato dai due chiamanti dall'utente autenticato. Il gemello Vision
(`estrai_dati_da_scontrino_vision`) legge l'utente solo da `st.session_state`, che in
produzione è il guscio vuoto: **nessun chiamante in produzione** (`handle_uploaded_files` è il
percorso Streamlit, zero invocazioni in `services/`, `worker/`, `scripts/`) — non toccato. Lo
script `_recupera_anteprime_offside_storiche.py` (OFFSIDE, un ristorante) resta a
`user_id=None`. Test: +7 in `tests/test_retail_anteprima_settore.py` (parser con settore
esplicito senza utente, esplicito che vince sull'utente, senza esplicito come prima; endpoint
anteprima; `upload_invoice` eseguito fino al ramo ambiguo con routing e RPC finti, per negozio
e per ristorante). **3 mutanti su 3 uccisi** (parser che ignora il settore, endpoint e ingresso
senza `settore`). Suite 13.498 verdi.

Dal reviewer, non bloccanti: la cache del settore è per processo (`invalida_cache` non
raggiunge il queue-worker, che vede un cambio settore entro 300 s: residuo esplicito, inerte
finché non esiste una sede retail); un rosso isolato in `test_home_briefing_cache_first.py`
alla prima passata, verde da solo e alla seconda — file non toccato dal branch, ordine dei
test, non regressione retail; la migration verificata sul live come **non applicata** (colonna
assente, funzione non aggiornata), coerente col vincolo.

### Settima lettura (code-reviewer sul cumulativo, 11/9 ore 00:46): verde

Nessun ottavo buco: il reviewer ha ripercorso ogni chiamante vivo di `estrai_dati_da_xml` (6),
`classifica_con_ai` (2), `categorizza_con_memoria` / `ottieni_categoria_prodotto` (tutti i
return passano da `_ret` / `_ret_ocp`), worker, admin, agente notturno, propagazione, Edge
Functions. Ha verificato che il fake di `upload_invoice` attraversa il percorso vero (mutando
la guardia magic-bytes i due test cadono) e che Vision è davvero morto (unico chiamante in
`legacy_streamlit/app_controllers.py`, mai importato da `services/`, `worker/`, `scripts/`).
Baseline a zero ×2, suite 13.498, `-m sql` 180, OpenAPI senza drift, 5.699 righe di test
aggiunte e 0 cancellate. Marker `.reviewer_gate_ok` scritto.

Residui nuovi, da tenere accanto alla cache 300 s: (1) le **anteprime già persistite** in
`fatture_queue.anteprima_righe` non si ri-parsano — un documento entrato in coda prima del
cambio settore mostrerà ancora food finché la cache non viene azzerata (inerte oggi: nessuna
sede retail esiste); (2) `_runtime_conferma_categoria` (`worker/queue_processor.py`) non ha il
gate settore: può solo confermare una categoria già proposta col gate, mai produrne una —
asimmetria, non presidio; (3) la **migration va misurata sul DB vivo** prima del push
(`information_schema.columns` per `ristoranti.tipo_attivita`, `pg_proc` per
`assegna_fattura_a_sede_tecnica`): il reviewer non ha avuto accesso.

**Bilancio Fase 1**: 14 commit, 16 file di test nuovi (5.699 righe), **69 mutanti uccisi, 1
sopravvissuto motivato** (quarta lettura: percorsi degradati, categoria retail già «Da
Classificare»), baseline a zero dopo ogni passo, 7 buchi trovati in 6 letture e chiusi.

**Etichette (gate 6)**: nella Fase 1 nessuna etichetta cliente cambia. L'unico testo nuovo sta
nel pannello **admin** (select «Settore», badge solo se retail), che non è un'interfaccia
cliente.

## Fase 2 — Prompt retail · Opus, ultrathink · **CHIUSA** 11/9/2026

Verificabile end-to-end **solo dopo 1.4**.

- [x] Prompt quasi binario: merce da rivendere / spesa di struttura,
      scelto per settore dove oggi si usa `PROMPT_CLASSIFICAZIONE_AI`
- [x] Replicare `tests/test_prompt_ai_coerenza_dominio.py` sul prompt retail:
      divieto NOTE, `Da Classificare` esplicito

**Chiusa l'11/9/2026 mattina.** `PROMPT_CLASSIFICAZIONE_RETAIL` in
`config/prompt_ai_potenziato.py`, accanto a quello dei ristoranti che resta
**letteralmente** intatto (3 righe rimosse in tutto il file: la vecchia firma della
funzione, riscritta col kwarg). `get_prompt_classificazione(articoli_json, settore=None)`:
kwarg additivo in coda, `None`/`'ristorazione'`/qualunque valore ignoto ritornano il testo
di oggi — fail-safe nella stessa direzione di `settore_service`. Cablaggio: **una riga**
in `services/ai_service.py:5393`, l'unico consumatore del prompt in tutto il repo
(`scripts/ab_test_modello_categorizzazione.py` non passa il settore: resta ristorazione).

**Il prompt, in sostanza**: cinque categorie e una domanda sola — *si rivende o serve a far
funzionare il negozio?* La distinzione non dipende dal prodotto ma dalla destinazione (lo
stesso martello è merce in una ferramenta e attrezzatura in una libreria), quindi il prompt
la fa decidere al **fornitore e al contesto della fattura**, non alla descrizione: se gli
indizi si contraddicono o mancano, `Da Classificare`. Divieto esplicito sulle categorie
alimentari, che per un negozio non esistono: un alimento venduto da un negozio è
`ARTICOLO DI VENDITA` come ogni altra merce.

**Scostamento dal punto di partenza, deliberato**: il piano elencava
`📝 NOTE E DICITURE` fra le uscite ammesse del prompt retail «solo a importo zero». Non lo
è: la categoria **non è in `categorie_ammesse('retail')`** (né in quella dei ristoranti) —
è riservata all'admin, arriva dal dizionario/L4 e non dall'AI, e la validazione a valle la
scarterebbe comunque. Il prompt retail quindi la **vieta**, esattamente come quello food:
regola di dominio #2 rispettata sui due lati. Uscite reali: `ARTICOLO DI VENDITA`, le 4
spese generali, `Da Classificare`.

Test (2 file nuovi, 28 test, **0 test esistenti toccati**):
`tests/test_retail_prompt_coerenza_dominio.py` (20) replica i 6 presidi di dominio sul
testo retail e aggiunge i vincoli del settore — nessuna food fra le uscite proposte,
l'elenco del prompt `==` `categorie_ammesse('retail') + Da Classificare`, nessun residuo
che parli di ristoranti, e l'uguaglianza letterale del prompt food;
`tests/test_retail_prompt_cablaggio.py` (8) esegue il classificatore vero con un client
finto e legge il `messages[0]["content"]` **davvero inviato**, prima chiamata **e retry**.

**11 mutanti su 11 uccisi**, uno per volta, `.bak` preso prima e md5 verificato dopo ogni
ripristino: prompt food sempre scelto; cablaggio che perde il settore; gate rovesciato (il
prompt retail ai ristoranti — 10 test rossi); retry che perde il settore; prompt che vieta
`Da Classificare`; food proposta come uscita; sesta categoria fuori whitelist; divieto NOTE
rimosso; grafia `Da Clasificare`; prompt che torna a parlare di ristoranti; categoria merce
rinominata. Due mutanti sono stati **rifatti perché invalidi**: uno mutava un commento
Python invece della costante (la riga trovata per numero stava sopra la `"""`), l'altro non
si era applicato affatto (assert fallito su `count == 1`: la stringa esiste in **entrambi**
i prompt) — in tutti e due i casi il verde non misurava niente, e senza il controllo
sarebbe stato scambiato per «presidio che regge».

**Un buco vero nel mio presidio, trovato dalla mutazione**: il regex copiato dal test food
guardava la *grafia* del divieto invece del suo senso, e restava **verde** con il divieto
scritto in chiaro davanti. Corretto normalizzando accenti e apostrofi e rendendo elastici
gli spazi. In fase lo avevo corretto **solo nel test nuovo**, perché
`test_prompt_ai_coerenza_dominio.py` è un test esistente; **chiuso anche lì l'11/9/2026 con
l'ok esplicito di Mattia**.

⚠️ La prima stesura di questo verbale diceva che il regex «cerca `NON è MAI` con la e
accentata, quindi è cieco all'apostrofo». **È falso e l'ha smentito la mutazione**: la
spiegazione esatta, con la tabella dei 5 mutanti, è in fondo alla sezione. Lasciata qui la
correzione perché era la prima cosa che si leggeva scorrendo dall'alto.

Gate: suite **13.526 verdi / 45 skip** (+28), `-m sql` **180**, `git diff main -- tests/`
**6.067 aggiunte / 0 cancellate** e nessun file di test modificato (in fase; l'unico test
esistente toccato è arrivato dopo, l'11/9, con l'ok esplicito), baseline `check` a zero
**×2** in processi nuovi (più uno subito dopo la modifica a `ai_service.py`), OpenAPI
**senza drift** (196 endpoint: il contratto HTTP non cambia, il settore si risolve dentro),
`check_documentazione.py` pulito. Nessuna etichetta cliente toccata: il prompt non è
un'interfaccia.

> **Cifra corretta dal reviewer**: avevo scritto «5.699 aggiunte» riprendendola dal bilancio
> di Fase 1 invece di ri-misurarla. Sono **6.067**: la differenza sono le due fixture JSON
> della baseline (`categorie_deterministiche.json` 3.477 + `costi_per_sede_mese.json` 226),
> che sono dati, non test. Il vincolo regge identico — 0 cancellate, 0 file in stato `M`.

### Ottava lettura (code-reviewer sul cumulativo, 11/9 ore 06:02): verde

Nessun ottavo buco nei percorsi eseguiti. Il reviewer ha ri-eseguito **tre mutanti** (dispatch
invertito → 10 rossi; settore perso al cablaggio `:5393` → 3 rossi; settore rimosso **solo**
dalla riga 5690 del retry → 2 rossi), verificando i md5 dopo il ripristino, e ha ripercorso
ogni chiamante vivo di `classifica_con_ai` / `_chiama_gpt_classificazione`. Ha riesaminato doc
e test **dopo** il commit doc `286dd6f` di una sessione parallela (solo `.md`, zero codice).

**Due residui nuovi, della stessa famiglia dei sette della Fase 1** — un `settore=None`
arrivato per una ragione che non c'entra col settore:

- `scripts/catscan_arbitro.py:32` e `scripts/catscan_senza_segnale.py:55` chiamano
  `classifica_con_ai(...)` **senza `settore`**: su righe di un negozio l'arbitro GPT verrebbe
  interrogato col prompt dei ristoranti. **Innocui oggi** — verificato che nessuno dei due
  scrive (nessun `.insert/.upsert/.update`, le sole occorrenze di `insert` sono
  `sys.path.insert`): sono diagnostici che stampano a video. Il danno sarebbe **una diagnosi
  sbagliata**, non dati sporchi.
- **Cosa li renderebbe nocivi**: (1) se il loro output venisse promosso a scrittura — è il
  precedente del 10/9, lo script «di sola lettura» che creò 308 voci; (2) più concreto, se
  venissero usati per **misurare la qualità della classificazione retail**: il loro verdetto
  «GPT diverge» sarebbe sistematicamente falso sui negozi, e si concluderebbe che il prompt
  retail funziona male quando non è stato nemmeno usato.
- **Quando guardarli: Fase 4** (è lì che si misura la qualità sui dati veri, quindi è lì che
  uno di questi script verrebbe rilanciato), e comunque prima della chiusura finale, insieme a
  `ricategorizza_sede*.py` e `_runtime_conferma_categoria`.

**Il limite del presidio food: chiuso l'11/9/2026 con l'ok esplicito di Mattia.** Era stato
lasciato come residuo perché il vincolo «nessun test esistente modificato» è il più forte della
fase; Mattia ha autorizzato la modifica prima di aprire la Fase 3.

`tests/test_prompt_ai_coerenza_dominio.py` ora normalizza accenti e apostrofi per riga, come il
gemello retail. **La causa era più stretta di come l'avevo scritta**: il regex non era cieco a
tutti i divieti con apostrofo — l'alternativa `MAI una risposta`, che l'accento non ce l'ha,
ne intercettava alcuni. Reggeva **per caso, non per costruzione**: bastava
`"Da Classificare" NON e' MAI valida` — né `NON è MAI` né `MAI una risposta` — e il divieto
passava davanti al presidio. La prima stesura del commento attribuiva il buco alla sola `è`
accentata, e la mutazione l'ha smentita: il primo mutante (`NON e' MAI una risposta`) veniva
ucciso **anche dal presidio vecchio**.

**Provato per mutazione, un mutante alla volta**, con `.bak` preso prima e md5 verificato dopo
ogni ripristino (`config/prompt_ai_potenziato.py` torna a `0f076c03…`, byte-identico):

| # | Mutante nel prompt food | Presidio vecchio | Presidio corretto |
|---|---|---|---|
| 1 | `"Da Classificare" NON e' MAI una risposta valida.` | ucciso (1 failed) | ucciso (1 failed) |
| 2 | `"Da Classificare" NON e' MAI valida: scegli sempre una categoria.` | **sopravvissuto (6 passed)** | **ucciso (1 failed)** |

Il mutante 2 è la prova del buco e della sua chiusura.

**Nona lettura del reviewer (11/9, `c83e44c`): lo stesso buco su un altro asse.** La
normalizzazione toglieva accenti e apostrofi ma **non collassava gli spazi**: dopo il replace
la riga diventa `NON  e  MAI` e il pattern letterale non matcha. Le alternative ora usano
`\s+`, in **entrambi** i test. Altri 3 mutanti, sulla costante viva con assert di avvenuta
applicazione:

| # | Mutante (grafia dello spazio) | Pattern precedente | Pattern elastico |
|---|---|---|---|
| 3 | `NON  e' MAI valida` (doppio spazio) | **sopravvissuto** | **ucciso** |
| 4 | `NON\te' MAI valida` (tab) | **sopravvissuto** | **ucciso** |
| 5 | `NON e' MAI valida` (spazio singolo) | ucciso | ucciso |

Falsi positivi sui prompt veri: **0 nel food, 0 nel retail**. Il reviewer ha ri-misurato la
tabella in autonomia e aggiunto un mutante suo (tripli spazi: stesso esito), rilevando che
`\s` matcha **anche `\n`**: a impedire che il presidio attraversi le righe non è il regex ma
`splitlines()`. Vale la pena saperlo prima di rimaneggiarlo.

**Un residuo consapevole, con l'accordo del reviewer**: il presidio è *polarity-blind* — farebbe
rosso su una riga legittima come `Inventare una categoria NON e' MAI accettabile: usa
"Da Classificare"`. Non lo restringo: inseguire la polarità con un regex lo rende fragile
proprio dove serve robusto, e l'errore «rosso su testo legittimo» si vede in un minuto, mentre
«verde sul divieto» è invisibile — in questo progetto è già costato il 29/8. Entrambi verificati nella **costante
viva** prima di leggere l'esito (`NON e' MAI` in `PROMPT_CLASSIFICAZIONE_AI` = True, nel retail
= False): un mutante che non si applica produce lo stesso verde di un presidio che regge.

Suite dopo la correzione: **13.526 verdi, 45 skip** — invariata. Il prompt food non è stato
toccato: l'unico file modificato è il test.

**Sullo scostamento NOTE E DICITURE il reviewer è d'accordo, con una ragione più forte della
mia**: per il retail una categoria fuori whitelist diventa `Da Classificare` **senza** recupero
deterministico (`ai_service.py:5472-5479`, a differenza del ramo ristorazione). Ammetterla nel
prompt avrebbe creato un'uscita che il modello vede come legittima e che il sistema rifiuta
**sempre**: un errore silenzioso auto-inflitto. E non lascia scoperto nulla — le diciture a
importo zero continuano ad arrivare da L4 / `classify_special_row_vectorized`, percorso **non**
gated per settore (in `worker/queue_processor.py` i soli gate retail sono a `:493` e `:551`),
quindi un negozio riceve `📝 NOTE E DICITURE` sulle righe a zero come prima, senza che l'AI
debba proporla.

> **Avvertenza del reviewer, da tenere**: non aver trovato l'ottavo buco non dimostra che non
> esista — dimostra che non è nei percorsi eseguiti. I sette della Fase 1 sono emersi in sei
> letture successive.

**Punto di partenza lasciato dalla Fase 1** (così la sessione non lo ri-cerca):
- Il prompt vive in `config/prompt_ai_potenziato.py` (`PROMPT_CLASSIFICAZIONE_AI`,
  `get_prompt_classificazione(articoli_json)`); l'unico consumatore è
  `_chiama_gpt_classificazione` in `services/ai_service.py`, che ha già il kwarg `settore` e
  lo usa solo per la **validazione** dell'uscita (`_categorie_ammesse_per(settore)`: per un
  negozio `ARTICOLO DI VENDITA` + le 4 spese generali; una food o una categoria inventata →
  «Da Classificare», nessun recupero dal dizionario). La scelta del prompt per settore va
  fatta lì: `get_prompt_classificazione(articoli_json, settore=settore)`, kwarg additivo, con
  `None`/'ristorazione' che ritorna **letteralmente** il testo di oggi (test: uguaglianza con
  `PROMPT_CLASSIFICAZIONE_AI`, non `in`).
- Per un negozio gli hint (`ottieni_hint_per_ai`) sono già `None`; safety net, override delle
  regole forti e guardrail IVA sono già spenti: il prompt retail è l'unica fonte di categoria
  oltre alla memoria locale del cliente.
- Uscite ammesse dal prompt retail: `ARTICOLO DI VENDITA`, le 4 di `CATEGORIE_SPESE_GENERALI`,
  `📝 NOTE E DICITURE` solo a importo zero, `Da Classificare` esplicito quando incerto.
- Test da scrivere (file nuovi, come sempre): la copia dei 6 test di
  `tests/test_prompt_ai_coerenza_dominio.py` sul testo retail; un test di cablaggio che catturi
  il prompt inviato al client finto (`_gpt` in `tests/test_retail_post_ai.py` registra
  `chat.completions.create`) per `settore='retail'` e per `None`; un mutante che faccia
  scegliere sempre il prompt dei ristoranti.
- La baseline (`retail_baseline.py check`) non chiama GPT: il vincolo sui ristoranti qui lo
  prova il test di uguaglianza del prompt, più la suite. Migration e deploy restano alla
  «Chiusura finale»: nessuna fase intermedia li richiede.

---

## Fase 3 — Spegnimenti ed etichette · Opus, ~2 giorni

**CHIUSA l'11/9/2026** — 4 commit (`5d9f367`, `c7e0d3b`, `dd6ac5e`, `c693a17`),
56 presidi nuovi in 3 file, **17 mutanti uno alla volta, tutti uccisi**.

- [x] Spenti per retail: ricette (`workspace/foodcost`), coperti (`margini/coperti`),
      **tab Centri di produzione** — fatti con il meccanismo dei flag per-tab
      dell'admin (`tab_off_*`), non con uno nuovo: stessa **convenzione inversa**
      (chiave presente = tab spenta), ed e' la ragione per cui i ristoranti non
      cambiano di una virgola — non hanno nessuna di quelle chiavi.
      `_normalize_pagine` **non e' stata toccata** (5 chiamanti e presidi che ne
      asseriscono la firma): gli spegnimenti stanno in `_pagine_con_settore`, che
      la avvolge. Il caso che conta e' `pagine_abilitate=None`, il default di
      quasi tutti gli account: per un ristorante resta `None`, per un negozio
      diventa la lista di tutte le pagine piu' i `tab_off`, o gli spegnimenti non
      arriverebbero mai al client.
- [x] Radar anomalie resta inerte (`anomaly_radar_service.py:51`, 5 categorie food):
      **verificato, non ereditato dal piano** — `CATEGORIE_CRITICHE` e' hardcoded e
      un solo chiamante (`invoice_service.py:2170`). Per un negozio il radar non
      trova nulla: feature muta, non un guasto. **Accettato e dichiarato.**
- [x] Etichette per settore. Centro unico in `lib/categorie-spesa.ts`
      (`tipoSpesaLabel`, `costoMerceLabel`, `filtroMerceLabel`, `attivitaLabel`):
      in tutte il settore e' **opzionale** e il ramo senza settore e' quello della
      ristorazione, cosi' un chiamante distratto mostra l'app di ieri invece di
      un'etichetta sbagliata a un cliente pagante. `TIPO_SPESA_LABEL` resta
      esportata e **letteralmente invariata**. Collegati: `spese-view` e il suo
      dialog, `agenda-overview`, i `TIPO_OPTIONS` di `articoli-tab` e `pivot-tab`,
      il fallback `"Ristorante"` del layout, l'hint «nel tuo locale» della pagina
      agenda e **`/m` a mano** (una sola etichetta hardcoded, meno del previsto).
      Dopo la review, corretto anche l'hint di `workspace/page.tsx`: nominava
      «ricette e foodcost», cioe' la tab che questa fase ha appena spento per un
      negozio — prometteva uno strumento inesistente. Resta fuori quello di
      `margini/page.tsx`, che e' **Fase 4** insieme alle soglie.
      Il settore arriva da `getCurrentUser()`.
      ⚠️ **Correzione dopo la seconda review**: avevo scritto «e' in `cache()` di
      React: **nessuna chiamata in piu' al worker**». **E' falso.** `cache()`
      deduplica le chiamate *nella stessa pagina*, ma il layout `(app)` usa
      `getCurrentSession` — una entry `cache()` **diversa**, sopra un
      `verifySession` che **non e' memoizzato** (`lib/auth.ts:90`). Ogni pagina
      che aggiunge `getCurrentUser()` paga quindi **un `/api/auth/me` in piu' per
      render**. Non e' una regressione di questa fase (`analisi-fatture`,
      `margini` e `catena` avevano gia' il pattern) e non cambia il
      comportamento, ma la frase agli atti era sbagliata. Se il costo dara'
      fastidio, il fix vero e' memoizzare `verifySession`, non togliere il
      settore dalle pagine: e' **lavoro a se', fuori da questa fase.**
- [x] Backend/export: **non fatto, e non per dimenticanza.**
      `margine_service.py` (`export_excel_margini`, `build_transposed_df`) ha
      **zero chiamanti in produzione** — codice Streamlit morto, e lo dichiara il
      repo stesso (`personale_export_service.py`: «nessun endpoint proprio, solo
      riferimento visivo»). Cambiarne le etichette avrebbe richiesto di toccare
      test esistenti per un risultato che nessun cliente vede.
      `routers/margini.py:824-828` e' `_KPI_SOGLIE_MARGINI`, che e' **Fase 4**
      (riga «Soglie: nessun colore per il retail in v1»): il nome `"Food Cost"`
      di `:1272` e' legato a quei testi, e rinominarlo ora lascerebbe un negozio a
      leggere mezzo testo da ristorante. Si fanno insieme, li'.
- [x] Liste categorie frontend. **Il buco vero non era nelle tre liste ma nel
      menu della catena**: `finestra-costi-gruppo.tsx` offriva `CATEGORIE_TUTTE` a
      chiunque, quindi a un negozio mostrava CARNE — che il backend, gated nella
      prima casella, rifiuta con **400**. Ora `categorieSelezionabili(settore)`,
      gemella di `categorie_ammesse(settore)`, **con un presidio che confronta le
      due**: se divergono fallisce il test invece del cliente.
      `ARTICOLO DI VENDITA` **non** entra in `CATEGORIE_TUTTE` ne' in
      `CATEGORIE_SPESA_FB/GENERALI` (il mutante 15 lo conferma: mettercela fa
      diventare rosso anche il presidio automatico preesistente). L'icona sta in
      `CATEGORIA_ICONS`, dove e' sicura — mappa per nome con fallback, non una
      partizione. Due correzioni: `🏷️` era il **fallback generico** (una voce che
      vale quanto la sua assenza) e `📦` gia' di MATERIALE DI CONSUMO; ora `🏪`,
      verificato senza collisioni.
- [x] Sei whitelist di scrittura su `categorie_ammesse(settore)`. **Quattro** ci
      passano (`fatture.py` batch e PATCH, `riparto.py` manuale e riga di gruppo
      via `normalizza_categoria_richiesta`, che prende un `settore` opzionale).
      **Due restano su `TUTTE_LE_CATEGORIE` di proposito**: ammettere li'
      ARTICOLO DI VENDITA creerebbe una voce in `prodotti_master` — la memoria
      dei ristoranti, che la Fase 1 ha gia' chiuso al retail — che nessun negozio
      puo' leggere. **Esclusione motivata, non dimenticanza.**
      ⚠️ **Correzione dopo la review**: la prima stesura diceva che entrambe
      «scrivono solo su `prodotti_master`». **E' falso per la seconda**:
      `admin_qualita_memoria_update` propaga anche sulle `fatture` di tutti i
      clienti, via `_propaga_global_override_a_fatture_storiche`. Resta sicura,
      ma per una ragione diversa da quella che avevo scritto — il filtro
      `settore_utente(uid) != SETTORE_RETAIL` che la **Fase 1** ha messo dentro
      quella funzione, prima dell'UPDATE. La conclusione regge, la motivazione
      era sbagliata.
      La whitelist della coda admin diventa l'**unione** dei due settori: senza,
      l'admin non poteva classificare la riga di un negozio da nessuna
      interfaccia (era il residuo dichiarato alla riga 536). Allargarla apriva
      pero' la direzione opposta — e il vincolo vale in entrambe: aggiunto il
      **gate speculare**, ARTICOLO DI VENDITA non raggiunge le righe di un
      ristorante in un gruppo misto.

### Cosa ha insegnato la mutazione (3 presidi su 56 erano finti)

| # | Mutante | Esito |
|---|---|---|
| 6 | `riparto_riga_categoria` senza settore | **SOPRAVVISSUTO** a 28 test verdi |
| 10 | chiave tab storpiata in `copertini` | sopravviveva al presidio scritto apposta |
| 12 | `!== "ristorazione"` invece di `=== "retail"` | ucciso dai presidi fail-safe |
| 15 | ARTICOLO DI VENDITA nelle liste condivise | ucciso **anche** dal presidio automatico |
| 17 | ristoranti che ricevono la lista del negozio | ucciso da 6 presidi |

1. **Il mutante 6 e' sopravvissuto** perche' il presidio era sulla funzione
   condivisa e non sull'endpoint. E i primi test scritti per ucciderlo erano
   sull'**endpoint sbagliato** — `riparto_manuale` invece di
   `riparto_riga_categoria`: stessa chiamata, funzione diversa. Vale
   [[mutante-va-mutato-nella-funzione-giusta]].
2. **Il mutante 10 ha smascherato un presidio finto**: il test scritto apposta per
   le chiavi inesistenti confrontava il TS con la lista attesa **scritta nel test**,
   e il mutante cambiava le due in blocco. Ora legge la costante viva, ed e'
   l'unico che uccide quel mutante da solo.
3. **Il presidio sui consumatori contava anche i commenti**, e falliva su due righe
   che *spiegano* l'etichetta: una guardia che grida su una spiegazione e tace su
   un bug scritto dentro un commento.
4. **Il mutante 12 e' quello che conta in produzione**: col confronto rovesciato un
   settore assente faceva scivolare un **ristorante** sulle etichette del negozio.
   E' il modo silenzioso in cui il vincolo si sarebbe rotto.

### Gate di fine fase

Suite **13.582** (da 13.526: +56 presidi, 0 esistenti toccati), `-m sql` **180**,
baseline **«Diff a zero»** dopo ogni casella, OpenAPI senza drift (196 endpoint),
`tsc --noEmit` pulito, `git diff main -- tests/` con cancellazioni **solo** su
`test_prompt_ai_coerenza_dominio.py` (l'unico autorizzato, Fase 2). I due presidi
automatici del vincolo (`test_spese_extra.py:238`,
`test_categorie_spesa_frontend.py:92`) **verdi**, e il mutante 15 prova che
sarebbero rossi se il vincolo venisse violato.

---

## Fase 4 — Briefing, chat AI, soglie · Opus normale · **CHIUSA** 11/09/2026

Commit: `23c0706` (chat: prompt + gate tool), `f76ddf1` (soglie, nome KPI,
frontend), `ec43fc2` (topic, script, bump briefing), `a6bb45d`, `e91f576`,
`d4867c0` (fix delle tre review). **241 presidi nuovi** (suite 13.582 →
**13.823**), **0 test esistenti toccati**, **43 mutanti** — 36 uccisi subito,
**7 sopravvissuti che hanno smascherato altrettanti presidi finti**, riscritti e
ri-mutati.

I **sei file di test nuovi** (nessun esistente toccato), con cui si ri-conta la
cifra sopra invece di ereditarla:

| File | Cosa presidia |
|---|---|
| `tests/test_chat_settore_retail.py` | prompt di sede e catena, gate tool, `/api/classify` |
| `tests/test_margini_soglie_settore.py` | soglie, nome KPI, i due endpoint margini |
| `tests/test_kpi_margini_frontend.py` | il match gauge↔commento, eseguendo il TS vero |
| `tests/test_briefing_topic_settore.py` | topic per settore e generazione della notifica |
| `tests/test_script_settore_retail.py` | i quattro script e il fallback sulla sede |
| `tests/test_wiring_settore_endpoint.py` | i gate nei **call site** — la lezione della fase |

```
python -m pytest tests/test_chat_settore_retail.py tests/test_margini_soglie_settore.py \
  tests/test_kpi_margini_frontend.py tests/test_briefing_topic_settore.py \
  tests/test_script_settore_retail.py tests/test_wiring_settore_endpoint.py -q
```

- [x] **Chat, blocco benchmark** — il prompt diceva «Rispondi SOLO a domande sui
      dati **del ristorante**» e hardcodava «soglia normale è 28-33%». Per il
      retail i benchmark non esistono (da ~35% a ~78% secondo cosa si vende): al
      loro posto il confronto coi propri mesi precedenti. Deviato anche il
      prompt di **catena** — un account retail multi-sede ci arriva davvero,
      perché quel gate conta le sedi, non il settore.
- [x] **Gate tool sul settore, non sulla pagina** — `_TOOL_VIETATI_PER_SETTORE`.
      Il gate è in **due punti**: la lista offerta al modello **e** l'esecuzione
      nel dispatcher, che esegue per nome e non consulta `tools` — un nome
      allucinato passerebbe il solo gate della lista.
- [x] **Briefing: `_CONFIG_TOPICS`** acquisisce il settore (`_topics_per_settore`).
      `coperti_anomalia` sparisce per un negozio; `fatturato_mancante` resta ma
      non promette più il food cost. Il gate è anche **dove la notifica nasce**,
      dentro `_briefing_dati_mensili_mancanti`: quello sulla lista non l'avrebbe
      tolta dalla campanella. `validi`/`bloccati` del POST restano sulla lista
      **completa** — il settore filtra cosa si vede, non cosa è salvabile.
- [x] **Bump `_BRIEFING_CODE_VERSION` 23 → 24** — cambia l'insieme delle
      notifiche nello snapshot.
- [x] **Soglie: nessun colore per il retail** (`_KPI_SENZA_SOGLIA_RETAIL`). Ma
      «nessun giudizio» non è «nessun commento»: la riga resta con l'emoji
      neutra, perché il frontend mappa l'**assenza** di commento sullo stesso
      gauge neutro — toglierla avrebbe spento il gauge. Personale, spese
      generali, MOL e primo margine restano giudicati: sono incidenze che non
      dipendono dal tipo di merce.
- [x] **Eredità della Fase 3**: nome KPI «Costo Merce» (`_nome_kpi_per_settore`),
      hint di `margini/page.tsx`, e `costoMerceLabel()` finalmente collegata —
      KPI Home, mobile `/m` incluso.
- [x] **Residui-script**: tutti e quattro, più `worker_client`.

### Il buco degli script era più profondo del residuo dichiarato

Il residuo diceva «chiamano `classifica_con_ai` senza settore». Eseguendo:

1. **sia `/api/classify` sia il fallback locale** risolvevano il settore SOLO da
   `user_id`. `ricategorizza_sede_ai.py` passa `user_id=None` e solo la sede:
   cadeva sul percorso ristorazione **per costruzione**. Aggiunto il fallback su
   `ristorante_id` in entrambi (l'account resta prioritario: è la fonte
   autorevole, la sede è il ripiego di chi non ce l'ha);
2. lo stesso script ha un punto **post-AI** (`_categoria_deterministica_runtime`)
   che **sovrascrive** l'esito dell'AI col dizionario. Senza gate lì, il filtro
   sul prompt sarebbe stato inutile;
3. **`ricategorizza_sede.py` non usa affatto l'AI**: chiama dizionario e regole
   forti direttamente, saltando il chokepoint `categorizza_con_memoria` dove la
   Fase 1 aveva messo il filtro d'uscita;
4. i due `catscan_*` raggruppano ora per settore: un chunk misto avrebbe avuto
   un solo prompt per clienti di settori diversi.

Tutti e quattro sono **la stessa famiglia dei sette buchi della Fase 1**: un
gate a monte che non copre il punto a valle. Si trovano **eseguendo**, non
leggendo.

### Cinque presidi finti, smascherati dalla mutazione

Non dalla rilettura. È il motivo per cui ogni presidio nuovo va mutato:

1. **il settore non arrivava dall'endpoint al prompt** — 20 test verdi
   misuravano la funzione, non il suo chiamante;
2. **`settore=` cercato in una finestra di 400 caratteri** dopo la chiamata: la
   finestra pescava il `settore=` della chiamata **successiva**. Riscritto
   sull'**AST**, guardando la singola `Call`;
3. **il vincolo del prompt ristorazione asseriva sei sottostringhe scelte** — ed
   era cieco proprio sulle quattro righe che avevo cambiato (vedi sotto). Ora
   confronta il prompt **intero** contro uno snapshot generato dal commit di
   ieri (`tests/fixtures/chat_prompt_ristorazione_pre_fase4.txt`), con le sole
   date a segnaposto, o sarebbe rosso domani senza che il codice cambi;
4. **la costante dei tool confrontata con se stessa** dopo che il mutante
   l'aveva già riscritta in place. Ora si misura che un RISTORANTE, chiamato
   DOPO un negozio, riceva ancora le descrizioni di ieri;
5. **`get_analisi_avanzata` non era coperto**: asserivo su
   `_valuta_soglia_margine`, non sull'endpoint;
6. **i quattro presidi su `_chat_tools_gruppo` chiamavano la funzione
   direttamente**, e il mutante che rimetteva `_CHAT_TOOLS_GRUPPO` al call site
   sopravviveva a tutta la suite;
7. **lo stesso, su `_topics_per_settore` e `_pagine_con_settore`** — trovati
   dalla terza lettura. Il secondo e' il piu' grave della fase: e' il gate
   della **Fase 3**, e con `pagine_abilitate` NULL (il default di quasi tutti
   gli account) un mutante al call site fa tornare `None`, quindi **nessun**
   `tab_off_*` raggiunge il client. Gli spegnimenti si sarebbero spenti in
   silenzio, a ogni login, con la suite verde.

**Quattro occorrenze dello stesso difetto in una fase sola** (il settore al
prompt, i tool di gruppo, i topic, le pagine), ogni volta col codice corretto e
il presidio che misurava la funzione invece del suo uso. La regola sta scritta
in testa a `tests/test_wiring_settore_endpoint.py`: **provare la funzione non
prova che qualcuno la usi** — per ogni gate si muta il CALL SITE, non il corpo.

### Il vincolo di Mattia è stato violato due volte, e ripristinato

- **Il tono «da collega esperto in F&B»**: l'avevo neutralizzato anche per i
  ristoranti. Rosso subito, ripristinato.
- **Quattro righe del prompt**, trovate dal `code-reviewer` generando il prompt
  sui due commit e confrontando gli md5 (11.081 → 11.064 byte). Una era pure
  **sgrammaticata in produzione**: «trainato principalmente **da il pesce**»,
  perché avevo sostituito un nome di voce dentro una frase senza la sua
  preposizione. La variante retail era corretta — il difetto esisteva **solo**
  dove non doveva esserci niente. Ora il prompt dei ristoranti ha lo **stesso
  md5** di ieri.

Nello stesso giro, **due affermazioni false nei miei commit**: che il ramo
ristorazione fosse «provato per uguaglianza» (asseriva sottostringhe), e che il
fallback sulla sede coprisse sia `/api/classify` sia il percorso locale (ne
copriva uno). Entrambe corrette in `a6bb45d`.

### Dichiarati, non chiusi

- **Il prompt di catena** per un negozio dice di ignorare la parte coperti di
  `gruppo_margini_coperti` invece di togliere il tool: toglierlo porterebbe via
  anche i margini, che al negozio servono. Stessa ragione per cui il gate non
  poteva stare sulle pagine.
- **La descrizione dei tool di gruppo** è deviata per settore, ma i tool di
  gruppo NON passano dal gate `_TOOL_VIETATI_PER_SETTORE`: il ramo catena esce
  prima. Oggi non c'è niente da spegnere lì.

### Gate di fine fase

Suite **13.823** verdi / 45 skip (da 13.582: **+241**, 0 esistenti toccati),
`git diff main -- tests/` con cancellazioni **solo** su
`test_prompt_ai_coerenza_dominio.py` (l'unico autorizzato, Fase 2), baseline
**«Diff a zero»** (56 righe di costi, 3.475 categorie) dopo ogni casella,
OpenAPI senza drift (**196 endpoint**), `tsc --noEmit` pulito, i due presidi
automatici del vincolo (`test_spese_extra.py:238`,
`test_categorie_spesa_frontend.py:92`) **verdi**. `-m sql` non rieseguito: la
fase non tocca SQL.

---

## Fase 5 — Sorveglianza post-deploy · Opus, ~mezza giornata

> **Perché esiste.** Le Fasi 1-4 hanno dimostrato il vincolo **al momento del
> commit**: baseline a zero, 241 presidi, 43 mutanti. Ma la baseline è una
> fotografia che scatta qualcuno a mano, e i presidi girano sul codice — non
> sui dati dei clienti dopo il deploy. Questa fase trasforma «l'abbiamo
> rispettato» in «sappiamo che regge», senza che serva una query manuale.
>
> **Il caso che deve intercettare**: una riga di un ristorante che cambia
> categoria per una ragione che non è un umano. È il danno peggiore che il
> retail può fare, ed è **silenzioso** — nessun errore, nessun test rosso, e il
> cliente lo scopre dal MOL sbagliato settimane dopo.

### Quello che esiste già, e NON va riscritto

Misurato sul branch l'11/9/2026:

- **`public.category_change_log`** registra ogni UPDATE che cambia
  `fatture.categoria`, via trigger `fn_log_category_change`
  (`supabase/migrations/20260429181500_add_category_change_log.sql` per la
  tabella, `20260908160000_registro_correzioni_attribuito.sql` per
  l'attribuzione). Colonne utili: `changed_at`, `ristorante_id`, `descrizione`,
  `old_categoria`, `new_categoria`, `actor_email`, `source`, `batch_id`.
  **Dal 8/9 lo scrittore si dichiara**: `source` distingue `correzione_cliente`,
  gli script (`script_ricategorizza_sede_ai`…) e il `db_trigger` anonimo.
  Prima di quella data 4.132 righe hanno `source='db_trigger'` e attore NULL:
  **il registro è utile solo da lì in avanti**, e la query va tarata di
  conseguenza — non si conta lo storico come se fosse attribuito.
- **`scripts/retail_baseline.py`** (`capture` / `check`): confronta costi e
  classificazione sui dati veri. È **manuale e puntuale**, e chiamarlo da un
  cron non basterebbe: confronta col file catturato, che invecchia. Serve come
  modello di *come si legge senza scrivere* (proxy + `pending_local_saves`),
  non come motore della sorveglianza.
- **Il pattern dei check periodici**: `.github/workflows/riparto_coerenza_check.yml`
  è il più vicino — cron giornaliero, `curl` a un endpoint admin del worker con
  `X-Worker-Key`, alert Telegram solo se il conteggio è diverso da zero, e un
  commento in testa che spiega **quale danno previene**. In
  `.github/workflows/` ce ne sono **12** in tutto, di cui 5 di sorveglianza
  (`*_check.yml`, `*_monitor.yml`): hanno tutti questa forma.

### Le caselle

- [x] **Misurare prima di progettare**: fatto, e ha **cambiato la forma della fase**
      (vedi sotto: l'attribuzione e' vuota, il segnale non poteva essere «senza attore»).
- [x] **Endpoint admin di sola lettura**: `GET /api/admin/retail/categorie-incoerenti`
      (`services/routers/admin.py`), forma `totale` + dettaglio come il gemello riparto.
- [x] **Workflow di sorveglianza**: `.github/workflows/retail_settore_check.yml`,
      cron 06:40 UTC, alert Telegram solo se `totale != 0`.
- [x] **Provato su un'anomalia vera**: il rosso e' costruito riga per riga su un
      Postgres vero (`tests/test_sql_retail_settore_incoerente.py`), non letto.
- [x] **Presidi con mutazione anche sul CALL SITE**: 11 mutanti, 1 presidio finto
      smascherato e corretto (dettaglio sotto).

### Due vincoli specifici di questa fase

1. **Sola lettura, come tutte le altre.** Un monitor che scrive è un monitor che
   può sbagliare sui dati veri. L'endpoint è `GET`, la query è `SELECT`.
2. **Il rumore uccide un monitor.** Un alert che scatta ogni giorno viene
   ignorato entro una settimana, e a quel punto non esiste più. Meglio una
   soglia che tace troppo di una che grida: la prima si stringe dopo aver visto
   i dati veri, la seconda non si riapre più.

---

### La misura ha cambiato la forma della fase

La prima casella — «misura, non fidarti del doc» — ha fatto cadere la premessa su cui
la fase era progettata. Il piano diceva: conta i cambi di categoria **senza un attore
umano**, leggendo `actor_email`/`source`. Misurato sul DB vivo l'11/09/2026:

| Fatto | Cifra |
|---|---|
| righe in `category_change_log` | **4.135** (4.022 su `fatture`, 113 su `prodotti_utente`) |
| righe **con** un attore | **0** — su tutte, comprese le 3 dopo l'8/9 |
| valori distinti di `source` | **1**: `db_trigger` |

Il doc diceva «dall'8/9 lo scrittore si dichiara»: le colonne esistono e la RPC
`aggiorna_categoria_fatture_attribuita` e' sul DB con tutti gli 8 argomenti, ma i GUC
che il trigger legge (`app.category_change_actor_*`) non li ha ancora valorizzati
nessuna scrittura reale — **nel repo non c'e' codice applicativo che li imposti**
(grep: compaiono solo dentro le migration). Un filtro su `actor_email IS NULL`
avrebbe quindi selezionato il **100%** delle righe: rumore puro, e un alert che
scatta ogni giorno viene ignorato entro una settimana.

**Il segnale e' quindi semantico e non basato sull'attore**: una riga di una sede
RISTORAZIONE che finisce in `ARTICOLO DI VENDITA` e' sbagliata **chiunque** l'abbia
scritta — un umano che sbaglia e' comunque una cosa da sapere. `actor_email` e
`source` viaggiano gia' nel dettaglio della response: quando l'attribuzione sara'
popolata, il filtro si stringe senza cambiare la forma.

**Perche' non fa rumore**, misurato sullo storico dei 4.022 cambi su `fatture`:
42,3% `Da Classificare` → categoria reale (lavoro normale), 55,7% reale → reale,
2,0% ritorno in coda. Il monitor **non guarda nessuna di queste classi**: guarda solo
l'incrocio fra categoria d'arrivo e settore della sede, che sullo storico completo
vale **0 righe** (0 cambi da/verso `ARTICOLO DI VENDITA` in 4.135). Tace finche' non
succede davvero.

### Cosa e' stato scritto

- `supabase/migrations/20260911170000_v_categorie_settore_incoerenti.sql` — la view,
  **scritta e non applicata** *(vero durante la fase; applicata poi alla Chiusura,
  l'11/9 sera)* — il vincolo di sola lettura valeva mentre si lavorava. Due classi:
  `ristorazione_con_categoria_retail` e la speculare `retail_con_categoria_food`.
  Legge `tipo_attivita` via `to_jsonb(r)->>` cosi' e' creabile **anche prima** della
  migration `20260910163000` (verificato: oggi la colonna non c'e', e tutte e 12 le
  sedi vengono lette come 'ristorazione', che e' il default di quella migration).
- `services/routers/admin.py` — l'endpoint, `GET`, query `SELECT`, nessuna scrittura.
  Finestra 24h (cap 720) e le due classi mai sommate in un numero solo.
- `.github/workflows/retail_settore_check.yml` — cron giornaliero 06:40 UTC (dieci
  minuti dopo `riparto_coerenza_check`, per non far partire due curl insieme).
  **Nessun secret nuovo**: `WORKER_SECRET_KEY` e i due Telegram esistono gia'.

### Mutazione: 18 mutanti (11 in stesura + 7 dopo le due review), e due hanno smascherato un presidio finto

Un mutante alla volta, `.bak` preso **prima** del primo, e ogni volta verificato col
`diff` che il mutante fosse **davvero applicato** prima di leggere l'esito.

| # | Mutante | Esito |
|---|---|---|
| 1 | la classe 1 si restringe a `old <> 'Da Classificare'` | ucciso |
| 2 | cade il filtro `tipo_attivita = 'ristorazione'` | ucciso |
| 3 | cade il filtro `table_name = 'fatture'` | ucciso |
| 4 | `CARNE` sparisce dalla lista food | ucciso |
| 5 | **la rotta viene smontata** (funzione intatta) | ucciso |
| 6 | la chiave `totale` rinominata | ucciso |
| 7 | le due classi sommate in un secchio solo | ucciso |
| 8 | cade il filtro sulla finestra temporale | ucciso |
| 9 | il workflow interroga un path sbagliato | **SOPRAVVISSUTO** → presidio riscritto |
| 10 | l'alert parte sempre (`if: always()`) | ucciso |
| 12 | la worker key sparisce dal curl | ucciso |
| 13 | il letterale `ARTICOLO DI VENDITA` diverge dalla costante | ucciso |
| 14 | `security_invoker` rimosso dalla view | ucciso |
| 15 | **la guardia per-rotta** rimossa (resta quella del router) | ucciso |
| 16 | **la guardia del router** rimossa (resta quella per-rotta) | ucciso |
| 17 | `to_jsonb(r)->>` sostituito da `r.tipo_attivita` | ucciso |
| 18 | la riga `ALTER VIEW ... security_invoker` **commentata** | **SOPRAVVISSUTO** al grep → presidio reso comportamentale |

**Il 9 e' la lezione della fase.** Il presidio asseriva `ROTTA in testo`: il path
compare **anche nel commento in testa al workflow**, quindi l'assert restava verde
con il `curl` puntato altrove — un monitor che riceve 404 e, per come e' scritto lo
step, si limita a loggare un errore: tacerebbe per sempre. E' esattamente
`assert-in-non-e-assert-uguale`. Riscritto per isolare **la riga del curl** e
confrontarla, poi ri-mutato (M9-bis): ucciso.

### Due difetti veri trovati dai presidi, non dalla lettura

1. **`?ore=0` allargava la finestra invece di stringerla**: `int(ore or DEFAULT)` —
   `0` e' falsy, quindi diventava 24. Corretto con `ore is not None`.
2. **L'endpoint non aveva una guardia propria**: `tests/test_router_dependencies_guardia.py`
   lo ha visto **solo nella suite intera** (girando il file da solo era verde).
   Il gate del router bastava oggi, ma se domani qualcuno togliesse quel
   `dependencies`, l'endpoint resterebbe scoperto. Aggiunto `Depends(_verify_worker_key)`
   esplicito: **nessun test modificato per questo**, era il codice a mancare.
   Il presidio che lo prova davvero e' arrivato solo dopo la review (M15/M16).

### L'unico test esistente toccato, autorizzato da Mattia

`tests/test_route_api_auth_dichiarativa.py`: **+8 righe, 0 cancellazioni**. E' la
allowlist `SENZA_IDENTITA_MOTIVATI`, e aggiungere una voce motivata e' il punto di
estensione **previsto dal test stesso** — nessuna asserzione e' stata cambiata, nessun
test adattato per farlo passare. La voce e' gemella di quella gia' presente per
`/api/admin/riparto/incoerenze`. L'alternativa (gate `_verify_admin`) e' stata
misurata e scartata **da Mattia**: in CI non esiste un bearer admin — tutti i workflow
di sorveglianza che colpiscono il worker usano solo `X-Worker-Key` — quindi avrebbe
reso il monitor irraggiungibile, cioe' l'obiettivo della fase mancato.

### La review: 🟢 alla prima lettura, e tre findings chiusi lo stesso

Il `code-reviewer` ha ri-misurato **tutte** le cifre di questo verbale e tornano
tutte. Nessun finding bloccante; i tre non bloccanti sono stati chiusi comunque,
perche' la migration non e' ancora applicata ed e' il momento piu' economico:

1. **`security_invoker` mancante** — era l'unica delle 4 view del repo a non
   averlo; la gemella `v_riparto_incoerenze` lo imposta con una ragione scritta
   (senza, `CREATE VIEW` eredita SECURITY DEFINER e bypassa RLS: 14 view chiuse
   per questo nell'audit del 20/6). Aggiunto, + presidio, mutato (M14): ucciso.
2. **Il letterale `'ARTICOLO DI VENDITA'` non era legato alla costante** —
   asimmetrico rispetto alla lista food, che il suo presidio ce l'aveva.
   Aggiunto il presidio gemello, mutato (M13): ucciso.
3. **La guardia per-rotta non era provata** — e il reviewer ha ragione: il test
   del 401 restava verde togliendola, perche' il gate del router copre comunque.
   Misurava la difesa del router, non quella aggiunta. FastAPI fonde le due
   dichiarazioni in una lista indistinguibile, quindi il presidio nuovo le
   **conta** (due = router + rotta). Mutato nei due sensi opposti — via la
   guardia della rotta (M15), via quella del router (M16): entrambi uccisi.

Il reviewer ha anche segnalato che **il caso «colonna `tipo_attivita` assente»
non era coperto da nessun presidio**: `conftest_sql` applica ogni migration con
prefisso >= alla data dello snapshot (08/09), quindi `20260910163000` e' sempre
gia' applicata e il caso non si esercita — pur essendo lo stato **reale del DB
oggi**. Chiuso con un test che toglie la colonna e ri-crea la view dentro la
transazione: mutato sostituendo `to_jsonb(r)->>` col riferimento diretto
`r.tipo_attivita`, com'e' naturale scriverlo (M17): ucciso.

### Seconda lettura: 🟢, e un presidio mio che sarebbe mentito

Il reviewer ha confermato i quattro presidi nuovi mutandoli lui, e ha misurato
una cosa che avevo sbagliato: **`test_la_view_dichiara_security_invoker` era un
grep sul sorgente**, e commentando la riga `ALTER VIEW` la view nasce senza
l'opzione mentre **32 test restano verdi** — il letterale sopravvive nel commento.
E' la stessa famiglia del mutante 9, ripresentata nel fix di un finding.
Sostituito con un presidio **comportamentale** che legge `pg_class.reloptions`
sulla view davvero creata (`-m sql`), e mutato col mutante esatto del reviewer
(M18, la riga commentata): ucciso.

Ha anche verificato — misurando, non deducendo — il rischio che avevo sollevato:
`security_invoker` **non rende cieco il monitor**, perche' `service_role` e'
`NOLOGIN BYPASSRLS` e BYPASSRLS si applica al ruolo invocante; con invoker il
worker continua a vedere le righe di tutti gli account (2 su 2 in prova).

**18 mutanti in tutto, 18 uccisi**, due dei quali (il 9 e il 18) sopravvissuti
alla prima stesura del rispettivo presidio e uccisi dopo averlo riscritto — ed
erano **lo stesso errore**: un assert che cerca un letterale nel sorgente invece
di misurare il comportamento.

### Gate di fine fase

Suite **13.873** verdi / 45 skip (da 13.840 dopo il rebase: **+33**), `-m sql`
**192** (da 180: +12, su Postgres vero), `git diff main -- tests/` con cancellazioni
**solo** su `test_prompt_ai_coerenza_dominio.py` (l'unico autorizzato, Fase 2),
baseline **«Diff a zero»** (56 righe di costi, 3.475 categorie) **due volte in
processi nuovi**, i due presidi automatici del vincolo verdi (83 test), OpenAPI
rigenerato e senza drift (**197 endpoint**, da 196), `check_documentazione.py` pulito.
Rebase su `main` fatto a inizio fase (5 commit di altre sessioni: login, GDPR, web;
nessuno tocca `ai_service.py`, `margine_service.py` o funzioni SQL, quindi la
baseline non andava ri-catturata — e infatti e' rimasta a zero).

### Dichiarati, non chiusi

- **~~La migration della view non e' applicata~~ — APPLICATA l'11/9 sera**, insieme
  a `20260910163000_add_tipo_attivita.sql`, con l'approvazione di Mattia. Era il
  residuo piu' pesante di questa fase: senza, l'endpoint avrebbe risposto 500 su una
  view inesistente al primo ridispiegamento di Railway. Misure dopo l'applicazione
  nel contratto «PRIMA DEL PUSH» in cima.
- **Il monitor non ha ancora visto rosso in produzione**, per costruzione: non
  esiste una sede retail. Ha visto rosso su Postgres vero (10 test), che e' il piu'
  vicino possibile finche' un negozio non esiste.
- **Nessuna CI ha mai visto questo codice**: il branch non e' mai stato pushato,
  quindi le 13.873 verdi sono locali. E' vero per tutto il branch, non solo per
  questa fase, e si chiude al push.
- **La view non ha `GRANT`**, come la gemella `v_riparto_incoerenze`: su Supabase
  dipende dalle default privileges. Da guardare **quando la migration verra'
  applicata** (memoria `revoke-from-public-non-basta-su-supabase`).
- **L'attribuzione resta da accendere**: finche' nessuno valorizza i GUC, il
  registro sa *cosa* e' cambiato ma non *chi* l'ha cambiato. Non blocca questa fase
  (il segnale non ne dipende), ma e' la ragione per cui il monitor non puo' oggi
  distinguere una correzione legittima dell'admin da una scrittura automatica.

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
mai `*` — `_SEDE_SELECT` (`routers/admin.py`) e `_resolve_sede_attiva`
(`fastapi_worker.py`). Il codice vecchio convive con la colonna nuova senza
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
- **Anteprime già in cache** e **cache settore per processo**: vedi «Settima lettura», residui.
- **Script diagnostici senza gate settore**: `scripts/catscan_arbitro.py:32`,
  `scripts/catscan_senza_segnale.py:55` (chiamano `classifica_con_ai` senza `settore`) e
  `scripts/ricategorizza_sede*.py`. Nessuno scrive: il danno è una diagnosi sbagliata su un
  cliente retail, non dati sporchi. **Da guardare in Fase 4**, prima di misurare la qualità
  della classificazione retail sui dati veri — vedi «Ottava lettura».
- **`test_documentazione_onesta.py` non scansiona questo file** (lista fissa di documenti):
  finché resta sul branch può mentire senza che un test lo dica. Al merge su `main` va
  aggiunto alla lista, o i suoi riferimenti a simboli e righe vanno ri-misurati a mano.

---

## Chiusura finale — quando tutte le fasi hanno passato il gate

**Eseguita l'11/09/2026 sera.** Tutte le caselle sono spuntate:

- [x] `git rebase main` e suite verde sul cumulativo — rebasato **due volte** (la
      seconda su `bb08c9f`, un commit GDPR arrivato da una sessione parallela mentre
      lavoravo): 13.877 verdi / 45 skip, `-m sql` 192, OpenAPI 197 senza drift
- [x] `/code-reviewer` sul cumulativo completo (47 commit), non sull'ultima fase: 🟢
- [x] Baseline «Diff a zero» **dopo** le migration, in processi nuovi
- [x] `CLAUDE.md`: `tipo_attivita` e' la **regola di dominio 7** (file a 199 righe,
      sotto il tetto che il suo test impone); questo file e' in `DOC_VIVI` di
      `tests/test_documentazione_onesta.py`
- [x] **Le DUE migration applicate sul DB** (approvate da Mattia passo passo), prima
      misurate pendenti e poi ri-misurate: 12 sedi su 12 `'ristorazione'`, view con
      `security_invoker=true` e 0 righe incoerenti sui dati veri
- [x] Commit portati su `main` con **rebase (fast-forward, nessun merge commit)**,
      branch `retail` eliminato, worktree rimosso
- [x] Memoria di progetto aggiornata, `docs/piani/PIANO_RETAIL.md` eliminato

- [x] **Push**, deciso da Mattia l'11/9 alle 20:14 UTC: 50 commit (49 del retail + 1
      GDPR di un'altra sessione; alla stesura della riga sopra erano 48, poi tre di
      sola documentazione). Sono partite **entrambe** le pipeline, Vercel e Railway.
- [x] **Misurato dopo il deploy**: worker su `2dbc77d`, Vercel READY, monitor `200`
      con `totale: 0`, zero scritture su fatture / prodotti / registro / sessioni /
      briefing / chat nei 20 minuti dopo il push, baseline «Diff a zero» di nuovo.
      Gli errori nei log (PostgREST «Thread killed by timeout manager», `/m` «worker
      error: 401») sono **precedenti al push** e con la stessa frequenza tutto il giorno.

**Rollback**, se mai servisse: tag `pre-deploy-retail-20260911` (= `283dcf2`, il commit
in produzione prima del push) + backup dati `~/oneflux-backup/20260910_105630`.

---

## Modello per fase

Default Opus. **Fable 5.1** dove l'errore è trasversale e silenzioso sui dati dei clienti,
non dove un test rosso lo segnala subito. A fine fase va detto esplicitamente che è chiusa,
così Mattia cambia modello a mano.

| Fase | Modello | Sforzo |
|---|---|---|
| 0 — snapshot, backup, worktree | Opus | **chiusa** 10/9 (`b642e3c`) |
| 1 — isolamento | **Fable** | **chiusa** 11/9 (`50fc209`) — ultrathink, un giorno invece di tre: 4 file condivisi, 12 punti di uscita, 7 buchi trovati in 6 letture e chiusi |
| 2 — prompt retail | Opus | **chiusa** 11/9 — ultrathink, mezza giornata: 11 mutanti, 1 buco nel presidio trovato mutando |
| 3 — spegnimenti ed etichette | Opus | normale — 2 giorni |
| 4 — briefing, chat, soglie | Opus | normale — 1 giorno |
| 5 — sorveglianza | Opus | **chiusa** 11/9 — normale, mezza giornata: 11 mutanti, 1 presidio finto |

Totale ~7,5 giorni. Fase 1 bloccante per tutte; 3 e 4 indipendenti fra loro.
