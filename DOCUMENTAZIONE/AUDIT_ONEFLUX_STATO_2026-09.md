# Stato audit ONEFLUX — ciclo aperto il 29/08/2026

**Dimensione «route API»: CHIUSA il 30/08/2026** (verbale in
`AUDIT_ONEFLUX_STATO_2026-08-29_STORICO.md`). Questo file sostituisce il ciclo 2026-08,
chiuso e archiviato in `docs/storico/` insieme al suo storico
(`AUDIT_ONEFLUX_STATO_2026-08.md` e `..._STORICO.md`).

> Il ciclo precedente si è chiuso con **8 decisioni aperte risolte in una
> sessione dedicata** il 29/8/2026 (radar anomalie, `normalizza_piva`, prompt
> AI, tipo spesa, Argon2, `p_limit`, riparto, commento `ai_pending`). Deploy
> Railway + Vercel su `fb5785fd`.
>
> Il nono punto (**F2-NOTEST**, test frontend) è stato **chiuso il 29/8/2026**
> nella sessione dedicata: vedi sotto. Il ciclo 2026-08 non ha più nulla di
> aperto.

---

## 🟢 Punto ereditato — CHIUSO il 29/08/2026

> **Mergiato e deployato la notte del 29→30/8/2026** (00:27 e 00:29 ora cliente,
> dentro la finestra consentita). PR #55 (test, nessun deploy) e PR #56
> (estrazione F7, deploy Vercel `success` alle 00:30). Merge commit `62d7593` e
> `0ed4fff`. Produzione verificata dopo il deploy: `/catena` redirige
> correttamente a `/login?next=/catena`, login 200.

**F2-NOTEST — nessun test runner frontend.** Deciso e implementato: **opzione A**
(test in `tests/*.py` che eseguono il TypeScript vero con node), non un runner
dedicato. Materiale preparatorio, archiviato col ciclo:
`docs/storico/AUDIT_ONEFLUX_STATO_2026-08_PUNTO_9.md` e `..._PUNTO_9_PROMPT.md`.

### Perché A e non Vitest

Ragione strutturale, non di gusto: `deploy-vercel.yml` scatta su `push: main`
con `paths: apps/web/**`, e non esiste `vercel.json` né `ignoreCommand`. Un
runner in `apps/web/package.json` significa che **ogni** merge di un test fa
partire un deploy di produzione: «ho cambiato un test» diventa indistinguibile
da «ho cambiato l'app». I test in `tests/` il workflow li ignora per costruzione.

Playwright (C) è stato escluso su un criterio preciso, non sul costo generico:
**non avrebbe preso nessuno dei due difetti di riferimento**. F1 produce una UI
plausibile ma sbagliata (serve un oracolo che l'E2E non ha) e F7 richiederebbe
500 descrizioni reali su account catena.

### La tecnica è cambiata: import vero, non regex

I due test storici estraevano una funzione con un regex e ne spogliavano la
firma con una `.replace()` letterale — che se la firma cambia **non fallisce**,
restituisce il sorgente invariato e node muore con un SyntaxError fuorviante. E
non attraversava gli `import`: per questo `categorie-spesa.ts`, che importa
`@/lib/admin`, era irraggiungibile.

Ora `tests/helpers_ts.py` importa il modulo di produzione vero con
`node --experimental-strip-types` + `module.registerHooks` per l'alias `@/`.
Verificato su **v22.15.0, v22.23.2** (ciò che `node-version: '22'` risolve) e
v24.19.0. Zero dipendenze npm, zero modifiche a CI/`pytest.ini`/`package.json`.

### Il risultato che ha deciso il design dei test

Prima di scrivere il test l'ho mutato: con fixture "ovvie" su `computeKpi`
(una scaduta nel 2020, una pagata, una nota di credito), **su 4 mutanti ne
moriva uno solo**. Sopravvivevano `scad < today`→`<=`, il filtro sul mese
corrente rimosso, e `new Date()` al posto di `parseLocalDate`. Un test dall'aria
del tutto sensata sarebbe entrato in CI verde coprendo quasi niente — esattamente
la «rete che sembra esserci e non c'è».

Con fixture **ai confini e relative a oggi** muoiono tutti e 6 i mutanti provati.
Ma il mutante del fuso muore **solo** con `TZ` a ovest di Greenwich: misurato,
con `Europe/Rome` sopravvive e con `Pacific/Kiritimati` (UTC+14) pure. Da qui la
parametrizzazione su `{Europe/Rome, America/Los_Angeles}` — Los Angeles non è un
fuso a caso e non è ridondante, ed è scritto nel docstring perché al primo
refactor nessuno lo tolga.

### Cosa c'è ora

| File | Contenuto |
|---|---|
| `tests/helpers_ts.py` | `esegui_ts()` + `node_o_fallisci()` (era duplicato nei 2 test storici) |
| `tests/test_categorie_spesa_frontend.py` | 43 test — F1, con **oracolo Python** (`_tipo_da_categoria`) |
| `tests/test_scadenziario_kpi_frontend.py` | 19 test — `computeKpi`/`bucketizeDocumenti`/`parseLocalDate`/`todayLocalIso`, confini + fusi |

### Cosa ha trovato il `code-reviewer` (e che è stato corretto)

Il gate ha trovato **un test che non asseriva quello che dichiarava**, esattamente
la classe di difetto che questo lavoro esiste per prevenire:

- `test_le_note_di_credito_non_sono_debiti` asseriva `1280 not in (k[c],)`, cioè
  che nessun totale valesse *esattamente* l'importo della nota di credito. Ma una
  NC che entra in un secchio ci entra **sommata**: col mutante che toglie
  l'esclusione, `da_pagare_totale` diventa 1590 e la riga passava lo stesso.
  Riscritta come confronto col campione privato della NC: ora fallisce da sola.
- `parseLocalDate` e `todayLocalIso` erano usate ma mai testate direttamente
  (`todayLocalIso` scrive `pagata_at` in produzione e ha già avuto un bug di
  fuso). Aggiunti i test; il mutante `getUTCDate()` richiede fusi agli estremi
  (`Pacific/Midway` −11, `Pacific/Kiritimati` +14) perché con i soli Rome/LA
  passerebbe o no **a seconda dell'ora in cui gira la suite**.
- Il confine dei 30 giorni era asserito solo dentro una somma, dove uno
  spostamento fra `mese` e `oltre` si compensa: ora i due bucket sono asseriti
  separatamente.
- La guardia anti-F1 non vedeva un array di oggetti né una union di tipi (la
  regex non attraversa l'annidamento). Riscritta su un criterio più semplice —
  il file nomina le 4 generali e **nessuna** F&B — e verificata contro tutte e
  tre le forme.

**E una CI rossa**: `test_i_kpi_non_dipendono_dal_fuso` confrontava tutti i KPI
di un campione unico valutato in due fusi. Ma fra le 22:00 e le 00:00 UTC Roma e
Los Angeles sono in **due giorni diversi**, quindi un documento «scade oggi» è
già scaduto per l'uno e non per l'altro — per costruzione, senza che il codice
abbia niente che non va. Il test era rosso ~2 ore su 24, e la «mitigazione» che
avevo scritto (ricostruire sul fuso più indietro) spostava il buco invece di
chiuderlo, perché il campione veniva poi valutato in entrambi. Riscritto: si
confrontano solo i KPI delle **pagate**, dove `pagata_at` è una data nuda che
vale lo stesso giorno ovunque. I bucket di scadenza dipendono legittimamente dal
"today" locale e non vanno confrontati fra fusi.

Mutanti provati in totale: **9**, tutti uccisi. Due erano stati "provati" con un
pattern che non matchava il sorgente: non applicavano nessuna mutazione, e il
loro "sopravvissuto" non voleva dire niente. Ri-eseguiti sul codice vero.

Il confronto di F1 è **comportamentale**, categoria per categoria, non fra
costanti: leggere due liste passerebbe anche se `tipoDaCategoria` invertisse il
ramo (provato: invertendolo cadono 38 test). Più una guardia che impedisce a F1
di riformarsi — cerca un file che *riderivi la divisione* FB/generali, non che
nomini qualche categoria: la prima stesura segnalava `admin.ts` (le 29
canoniche), `periodi.ts` (mappa di icone) e `demo-data.ts` (righe finte), tutti
legittimi. Ricreando il difetto la guardia scatta.

### Cosa NON copriamo — dichiarato

Rendering React, hook, stato, effetti, `useMemo`, routing, CSS, accessibilità,
integrazione API reale, e tutto ciò che sta fuori da `lib/` (~47.500 righe).
Copriamo **logica pura in moduli senza React**.

**`poolSaturo` (F7): coperto, in una PR separata.** Viveva dentro un `useMemo`
anonimo in `gruppo-tag-section.tsx`, dove nessuna tecnica lo raggiungeva.
Estratto in `apps/web/src/lib/tag-candidati.ts` (`calcolaCandidati`), con
`RPC_LIMITE_DESCRIZIONI` allineata al `p_limit` di `routers/gruppo.py` — non è
la «fonte unica»: il 500 vive in **tre** posti indipendenti (il router, il
DEFAULT della funzione SQL, la costante client), e un test confronta il valore
client col router perché la divergenza non resti invisibile. 12 test, e **reintrodurre il difetto originale
(`pool.length` invece di `risposta.length`) li fa fallire**.

Il refactor è provato equivalente, non solo `tsc`-pulito: vecchia e nuova
implementazione confrontate su **504 combinazioni** di pool/associate/filtro
(0 divergenze). Tenuto in una PR separata perché tocca `apps/web/**` e quindi
fa partire il deploy Vercel.

Resta scoperto, e dichiarato nel docstring del test: che il *componente* passi
`risposta` e non il pool filtrato. Il componente non è testato (nessun
rendering). Mitigazione a costo zero: il parametro si chiama `risposta`, è il
primo, e nel componente non esiste più una variabile filtrata prima della
chiamata.

### Correzione al documento preparatorio

Il dossier citava `margini.ts` come «dove sta il calcolo dei
numeri del cliente»: **falso**, contiene solo tipi e wrapper `fetch`, il calcolo
è server-side. Gran parte di `lib/` è così — la superficie di logica pura reale è
ben minore delle 3.339 righe. Corretto nel documento.

Le altre cifre del documento sono state ri-misurate e reggono tutte: 399 file,
50.891 righe, 3.339 in `lib/`, zero runner, 55 test node preesistenti.

---

## 📊 Il perimetro ancora scoperto — misurato il 30/08/2026

> ⚠️ **Questa tabella è parziale, e il 31/8 si è misurato quanto.** Elenca
> **4 aree frontend su 14** e **zero backend Python**: 15.049 righe su 110.419.
> Il conto completo sta in **`AUDIT_COPERTURA.md`** — 35% letto integralmente,
> 16% auditato per dimensione, **49% mai guardato**. Usa il contatore per
> decidere le priorità, non questa tabella.
>
> **Aggiornato l'1/9 (3 passate nella stessa giornata):** `(app)/catena/` è
> **chiusa** — 2.800 righe su 2.938 (**95%**), misurate a fine giornata. La
> logica sta in `lib/catena-confronti.ts`, `catena-tag.ts`,
> `catena-costi-gruppo.ts` e `catena-export.ts`: **283 test** (contati con
> `--collect-only`, non a mente: le stesure precedenti dicevano 267 e 280).
>
> ⚠️ **La 2ª passata l'aveva dichiarata chiusa al 90%, e non lo era.** Contava
> come coperti `finestra-margini-coperti.tsx` e `finestra-spesa-pv.tsx` perché
> *importavano* da `lib/`, mentre ~55 righe di export Excel vivevano ancora
> dentro `exportXls()`, irraggiungibili. **Il criterio «il file importa da lib/»
> non è «la logica del file è in lib/»**: un file può essere coperto a metà e la
> tabella non se ne accorge. La 3ª passata li ha estratti in `catena-export.ts`.
>
> **Restano scoperte 138 righe**, nessuna con logica: `card-segnali.tsx` (110,
> fetch + JSX) e `loading.tsx` (28, skeleton). `page.tsx` è stato chiuso nella
> stessa sessione estraendo le sue due decisioni — chi **vede** la modalità
> catena (`num_pv < 2 → redirect`) e chi vede la chat AI — come predicati puri
> in `catena-confronti.ts`. La copertura è sulla **logica pura, non sul
> rendering**: `esegui_ts` non monta React.
>
> Tre esiti che valgono oltre l'area: `replaceAll` **non** è il fix del bug
> sull'importo italiano (a rompere è il punto delle migliaia, non la virgola —
> ricetta verificata nel verbale); la guardia sulle liste vuote di
> `config-assistente-catena` resta aperta come fix a sé; e la 3ª passata ha
> trovato che **`helpers_ts.py` era cieco a ogni argomento negativo scalare**
> (node leggeva `-2.675` come flag → `rc=9`, stderr vuoto). Corretto alla fonte:
> vale per tutti i 12 file di test frontend, non solo per catena.
>
> **1/9 pomeriggio — i bug fotografati sono stati CORRETTI**, su richiesta
> esplicita dell'owner. Non è più «in attesa di una finestra»:
>
> - **L'importo italiano**: era in **60 punti**, non ~25 come diceva il verbale.
>   E nella pagina dei ricavi usava `parseFloat`, che è **peggio** di `Number`:
>   su `"1.234,56"` non dà NaN ma `1.234`, quindi nessun errore e un fatturato
>   entrava nel MOL come 1,23 €. Fonte unica in `lib/format.ts`, **due varianti**
>   perché il punto non significa la stessa cosa ovunque (`parseNumeroIt` per gli
>   importi, `parseDecimaleIt` per ore/percentuali/costi orari): tutti i 58 punti
>   classificati uno per uno.
> - **L'arrotondamento** (`arrotonda2`): il mezzo centesimo ora sale sempre ed è
>   simmetrico. Prima `1.005 → 1` e `-2.675 → -2.67`, due regole diverse.
> - **Un terzo bug trovato durante le verifiche**: `−1.234,56` col meno unicode
>   (U+2212, quello che arriva incollando da Word/Excel/PDF) dava NaN. Una nota
>   di credito incollata veniva rifiutata.
>
> ⚠️ **Il backend non fa da rete**: `RicavoGiornalieroItem` dichiara
> `fatturato_iva10: float` senza `ge`/`le`, e i router leggono `float(x or 0)`.
> Il parser del frontend era l'unica difesa. Vale la pena valutare una
> validazione server-side come dimensione a sé.
>
> `margini/` (4.709, il MOL) e `scadenziario/` erano state chiuse il 31/8.
> `workspace/` (5.012) resta 🟠 37%, col resto escluso con misura nel ciclo 08.
> **Non esiste più un'area frontend grande mai toccata**; le 🔴 rimaste sono
> `(app)/` altre 7 aree (4.250), `(auth)/(legal)/(demo)` (1.353) e
> `hooks/`+`proxy.ts` (622).

Superficie oggi (`wc -l`, rimisurata, non ereditata):

| Perimetro | Righe |
|---|---|
| Python runtime (`services/`,`utils/`,`config/`,`worker/`) | 55.432 |
| Frontend `apps/web/src/` | 51.614 |
| Edge Functions | 3.556 (✅ coperte) |

**Le aree che nessuna fase del ciclo 2026-08 ha aperto**, con l'esposizione live
misurata sul DB (progetto `vthikmfpywilukizputn`, 30/8/2026):

| Area | Righe | Esposizione live | Priorità |
|---|---|---|---|
| ~~**169 route API** (`apps/web/src/app/api/`)~~ | 4.776 | tutto il traffico dell'app | ✅ 30/8 |
| `scadenziario/` | 2.212 (client 2.118) | **2.001 doc non pagati**, 1.853 scaduti, 148 futuri, 32 pagate/30gg | ✅ **chiusa 31/8 (2ª sessione)**: filtri/ordinamento/stato estratti in `lib/` e provati per mutazione (17 uccisi su 18, 1 dichiarato). Resta scoperto il solo rendering |
| `prezzi/` | 2.361 (5 tab) | **39.133 righe fattura** a monte | 🟠 |
| `admin/` | 3.685 | solo staff, non clienti | 🟡 |
| `assistenza/` | 292 | `marketplace_leads` 0 righe | ⚪ |

> **Perché le route API per prime.** F2 del ciclo scorso ha trovato lì 2 dei 4
> difetti della fase, incluso l'unico HIGH (open redirect), e il perimetro
> dichiarato non le conteneva: erano «le pagine, non il percorso». 169 route
> non sono mai state auditate come layer proprio. `admin` ne ha 41, `workspace`
> 30, `scadenziario` 9.

> **ESITO 30/8/2026 — le tre ipotesi erano false.** L'audit ha misurato: 0 body
> grezzi su 114 POST (tutto Pydantic), 0 route che leggono `ristorante_id` dal
> client, 48/50 select su `fatture` che filtrano il soft-delete, nessun IDOR
> raggiungibile da non-admin. Il layer Next è un proxy trasparente (0/169 route
> toccano il DB): l'autorizzazione vive tutta nel worker. Il rischio vero era
> **strutturale** — 228/238 endpoint risolvono l'identità nel corpo
> dell'handler, con 12 `APIRouter()` nudi: default aperto. Chiuso con
> `tests/test_route_api_auth_dichiarativa.py` (9 test, 6 mutanti uccisi).
> **Resta aperto**: alzare `dependencies=[...]` a livello di router.

> **Perché lo scadenziario subito dopo.** È l'area con più dati vivi non ancora
> letta: 2.001 documenti non pagati, di cui 1.853 già scaduti. È anche l'unica
> con **2.244 righe in un solo file**, e ha già avuto un difetto di fuso su
> `pagata_at` (il ciclo 2026-08 l'ha corretto lato scrittura; la UI che lo legge
> non è mai stata auditata).
>
> **Copertura già esistente, misurata il 31/08/2026 — non è terra vergine.**
> `python -m pytest` sui 5 file scadenziario → **69 passed in 12s**:
>
> | File | Test | Cosa copre |
> |---|---|---|
> | `test_documenti_service_rid_e_regole.py` | 19 | Step 3 di `get_documenti_scadenziario`, regole `attiva`, `pagata_manuale_at` |
> | `test_chat_query_scadenze.py` | 12 | query scadenze via chat |
> | `test_documenti_service_scadenziario.py` | 10 | RPC `scadenziario_fatture_aggregate`, multi-sede |
> | `test_scadenziario_kpi_frontend.py` | 19 (9 def × fusi) | `computeKpi`, `bucketizeDocumenti`, `parseLocalDate`, `todayLocalIso` |
> | `test_gruppo_scadenziario_fatture.py` | 9 | scadenziario di gruppo/catena |
>
> Il **backend è coperto**, e il **difetto di fuso è coperto in lettura**: le 4
> funzioni esercitate dal test frontend sono tutte e sole le funzioni logiche
> esportate da `lib/scadenziario.ts` (le altre export sono tipi, `MODALITA_LABELS`,
> un re-export di `formatEuro` e `formatDate`). La roadmap diceva «i test del
> punto 9 coprono `computeKpi` e `bucketizeDocumenti`»: **sono 4 funzioni su 4**,
> non 2, e su 2 fusi.
>
> **Quel che resta scoperto è solo `scadenziario-client.tsx` (2.244 righe):**
> rendering, stato, hook, effetti, filtri client. Cioè esattamente ciò che il
> punto 9 dichiara fuori perimetro per costruzione («Rendering React, hook,
> stato, effetti, `useMemo`»), e che nessuna delle tecniche adottate raggiunge
> senza estrarre la logica in `lib/` — la strada già battuta con `poolSaturo`/F7.
>
> **Conseguenza sulla priorità:** la dimensione è più piccola di come è scritta
> in tabella. Non è «2.337 righe mai lette», è **un solo componente di UI**, con
> il resto già in rete. Il lavoro utile è *estrarre e coprire*, non *auditare da
> zero*.
>
> **Primo pezzo fatto il 31/08/2026.** `buildCashFlow` — la funzione che decide
> quanto denaro l'utente vede in ciascuna fascia di esposizione futura — viveva
> dentro il componente, irraggiungibile da qualunque test. Estratta in
> `lib/scadenziario.ts` (corpo **identico riga per riga**, verificato con `diff`),
> coperta da 8 test su fixture ai confini esatti, **4 mutanti uccisi** — compreso
> `new Date()` al posto di `parseLocalDate`, cioè il difetto storico di fuso, ora
> coperto anche sulla barra cash-flow. Un test tiene allineate le **tre**
> implementazioni degli stessi confini (`computeKpi`, `bucketizeDocumenti`,
> `buildCashFlow`), che ricalcolano ciascuna il proprio `today`.
>
> `scadenziario-client.tsx`: 2.244 → **2.210 righe** ancora non testate
> (rendering, stato, hook, filtri client). Verbale nello storico.
>
> ```bash
> python -m pytest tests/test_scadenziario_kpi_frontend.py \
>   tests/test_documenti_service_scadenziario.py \
>   tests/test_documenti_service_rid_e_regole.py \
>   tests/test_chat_query_scadenze.py \
>   tests/test_gruppo_scadenziario_fatture.py -q
> ```

## Voci aperte ereditate — ri-misurate il 31/08/2026: 2 su 3 erano false

> **Lezione, non contabilità.** Queste tre voci erano marcate «verificate ancora
> vere il 30/8/2026». Ri-misurate il 31/8 **una per una col comando accanto**,
> due non reggono. Erano già state riprese per buone all'inizio della sessione
> del 31/8 e hanno prodotto lavoro fantasma finché la misura non le ha smontate:
> è esattamente il modo in cui un documento sempre in contesto propaga i propri
> errori. Restano scritte qui, smentite e non cancellate, perché la smentita
> vale più della voce.

1. ~~**Il blocco notifiche `source_type='upload'` è morto.**~~ **FUORVIANTE.**
   Non è codice morto: è **irraggiungibile per costruzione**, ed è già
   documentato nel repo. Le 7 `build_notification_record`
   (`upload_handler.py:1987-2080`) vivono dentro `handle_uploaded_files`
   (`:897`), il cui **unico** chiamante è `legacy_streamlit/app_controllers.py:1701`
   — modulo che importa `streamlit` vero, **non installato** (vedi CLAUDE.md e
   `services/_streamlit_shim.py`). Il blocco legge
   `st.session_state.get('ristorante_id')`: sullo shim è un dict vuoto, quindi
   `_inbox_rid` resta `""` e la guardia `if _inbox_uid and _inbox_rid` non passa
   mai. **La data «1/6/2026» non è un guasto da indagare: è la dismissione di
   Streamlit.** Cinque test lo dichiarano già escluso per misura
   (`test_radar_aggancio_percorso_vivo.py`, `test_invoice_vision.py`,
   `test_td24.py`, `test_upload_handler_pagination.py`, `upload_policy.py:4`).
   Nessuna azione: lo stato è già scritto dove serve, cioè nel codice.

   ```bash
   grep -rn "handle_uploaded_files" --include=*.py . | grep -v tests/
   ```

2. ~~**`check_weekly`** — zero chiamanti, da agganciare o rimuovere~~
   **CHIUSA il 31/08/2026: la domanda era mal posta.** Zero chiamanti confermato,
   ma agganciarlo **non produrrebbe nulla**: è una **catena morta a due anelli**.
   `check_weekly` legge `notification_inbox` con `topic_key='price_alert'`, e
   l'unico emettitore di quel topic è `upload_handler.py:2019` — dentro
   `handle_uploaded_files`, cioè il percorso `legacy_streamlit` già dichiarato
   morto. Sul DB live: **3 righe `price_alert`, tutte `source_type='upload'`,
   l'ultima 1/6/2026** (la dismissione di Streamlit).

   Quindi schedularlo domani leggerebbe 0 righe e tornerebbe `[]` per sempre.
   **Né agganciato né rimosso**: la logica (`fornitore_critico_consecutivo`) è
   scritta e testata, manca il *produttore* a monte. Il radar vivo
   (`check_on_upload`) oggi emette altri tre topic.

   Non è più una voce di roadmap perché **il fatto è ora nel codice e in una
   rete**: docstring di `anomaly_radar_service.py` + 2 test in
   `test_radar_aggancio_percorso_vivo.py` (via **AST**, non match testuale) che
   falliscono se qualcuno aggancia `check_weekly` **o** se nasce un sorgente
   nuovo di `price_alert` — nel secondo caso la notizia è buona, e la decisione
   va ripresa. I due sorgenti noti (`upload_handler.py`, percorso legacy; e
   `fastapi_worker.py:6443`, dict in memoria che non persiste) sono in allowlist
   con la loro ragione.

   ```sql
   SELECT topic_key, source_type, count(*), max(created_at)::date
   FROM notification_inbox GROUP BY 1,2 ORDER BY 3 DESC;
   ```

3. ~~**`normalizza_descrizione`** — 5 pattern su 7~~ **FALSO.** La funzione
   (`utils/text_utils.py:115`) applica **tutti e 7** gli step, e tutte e sei le
   costanti `REGEX_*` che usa esistono, sono importate (`:17-22`) e sono
   popolate: `REGEX_UNITA_MISURA` 30 pattern, `REGEX_SOSTITUZIONI` 19,
   `REGEX_ARTICOLI` 10, più tre regex singole. Nessun residuo del ciclo 2026-07.
   **Voce chiusa.**

   ```bash
   python3 -c "import utils.text_utils as t; print(len(t.REGEX_UNITA_MISURA), len(t.REGEX_SOSTITUZIONI), len(t.REGEX_ARTICOLI))"
   ```

**Baseline radar da sorvegliare**: `notification_inbox` ha **0 record
`source_type='radar'`** su 65 totali (30/8). Il radar è stato ricollegato il
29/8: dopo i primi upload reali dovrebbero comparirne **pochi e veri**. Se ne
compaiono molti, la ritaratura su `numero_documento` va rivista — prima del fix
ne avrebbe prodotti 897, tutti falsi.

---

## Come si apre una dimensione qui

Il protocollo è invariato rispetto ai due cicli precedenti — vale la pena
rileggerlo in `docs/storico/AUDIT_ONEFLUX_STATO_2026-08.md` §«COME SI USA QUESTO
FILE» prima di iniziare. In sintesi:

1. Una dimensione per sessione, autosufficiente (perimetro misurato, ipotesi,
   criterio di chiusura, comandi).
2. Audit **read-only** prima di ogni fix; remediation solo dopo conferma.
3. **Ogni severità e ogni cifra si ri-misurano sul DB live al momento di
   scriverle.** Nel ciclo 2026-07 è caduta 8 volte una severità ereditata; nel
   2026-08 il `code-reviewer` ha trovato un errore in **ogni** fase; nella
   sessione degli 8 punti ri-misurare ha corretto la roadmap **quattro volte**,
   e in tre casi ha cambiato il lavoro, non solo il racconto.
4. Ogni fix nuovo → **provato per mutazione, su copia in scratchpad**: si rimuove
   il fix e si controlla che i test tornino rossi. Un test che non fallisce
   quando il difetto torna non è una rete.
5. `code-reviewer` sul diff cumulativo a fine sessione, **sempre**.
6. Prima di dichiarare chiusa una fase: `gh pr view <n> --json headRefOid`
   contro `git log -1`, e CI verde **su GitHub**, non solo in locale (la CI gira
   su Python 3.12 con `requirements-lock.txt` e un gate
   `coverage --fail-under=45`: non è lo stesso segnale del verde locale).

---

## Lezioni trasversali da non ri-imparare

Le 36+ lezioni operative dei cicli precedenti stanno negli storici. Le tre che
hanno morso più di recente:

- **Un mock generoso è un test che mente.** I 6 test del radar anomalie sono
  stati verdi per mesi su una query che filtrava una colonna inesistente, perché
  il fake restituiva `self` da ogni builder ignorando gli argomenti. Un fake che
  valida i nomi di colonna contro lo schema reale l'avrebbe intercettato il primo
  giorno.
- **Leggere un `if` non dice quale suo lato è caldo.** Il `tipo` spesa sembrava
  protetto leggendo il codice; il 97,77% dell'importo reale passava dall'altro
  ramo.
- **Codice morto che resta chiamabile è un difetto latente.** Cambiare una firma
  senza aggiornare un call site irraggiungibile non rompe la produzione, ma
  l'`except` che lo avvolge silenzia l'errore — lo stesso meccanismo che aveva
  reso invisibile il difetto originale.
