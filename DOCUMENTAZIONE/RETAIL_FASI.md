# Retail — le fasi dell'implementazione

Stato al **10/09/2026, sera**: Fase 0 chiusa (`b642e3c`); **1.1 e 1.2 chiuse** (gate 4-5
passato: due check a zero dopo il fix di paginazione `da269ad` su `main` e la
ri-cattura della baseline, vedi «Trovato durante la 1.1»); **1.3-1.7 chiuse**; gate 1-8 e 10
passati; gate 9: sei letture (cinque del reviewer, una a mano) hanno trovato **sette buchi
della stessa famiglia, tutti chiusi** (vedi le sezioni «lettura», dalla seconda alla sesta);
**settima passata del reviewer verde** (10/9 ore 23:00, cumulativo di 14 commit, codice a
`50fc209`). **Fase 1 CHIUSA.** Prossima: Fase 2 con Opus, ultrathink.

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

**Aggiornamento 10/9 sera**: il fatto non spiegato È spiegato — vedi «Trovato durante la
1.1». Due check verdi di fila (16:20) non erano una prova: la lettura sbagliata capita
~2 volte su 10.

---

## Fase 1 — Isolamento · **bloccante per tutte le altre** · Fable, ultrathink · **CHIUSA** 10/9/2026 (`50fc209`)

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
arbitrario). Sui dati veri cambia **1 riga su 3.475** (Villa Guardia, GIUGNO: BIRRE →
SERVIZI E CONSULENZE, cioè verso la correzione manuale del cliente). La baseline è stata
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
in PIANO_RETAIL.md, da chiudere prima che esista una sede retail. Test: +10 in `tests/test_retail_guardrail_iva.py` (guardrail da solo, wrapper,
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

### Settima lettura (code-reviewer sul cumulativo, 10/9 ore 23:00): verde

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
| 1 — isolamento | **Fable** | **chiusa** 10/9 (`50fc209`) — ultrathink, un giorno invece di tre: 4 file condivisi, 12 punti di uscita, 7 buchi trovati in 6 letture e chiusi |
| 2 — prompt retail | Opus | **ultrathink** — 1 giorno: regola di dominio #1 |
| 3 — spegnimenti ed etichette | Opus | normale — 2 giorni |
| 4 — briefing, chat, soglie | Opus | normale — 1 giorno |
| 5 — sorveglianza | Opus | normale — mezza giornata |

Totale ~7,5 giorni. Fase 1 bloccante per tutte; 3 e 4 indipendenti fra loro.
