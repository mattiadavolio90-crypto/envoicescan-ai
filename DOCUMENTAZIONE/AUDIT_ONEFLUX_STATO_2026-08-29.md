# Stato audit ONEFLUX — ciclo aperto il 29/08/2026

**Nessuna dimensione ancora aperta.** Questo file sostituisce il ciclo 2026-08,
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

**F2-NOTEST — nessun test runner frontend.** Deciso e implementato: **opzione A**
(test in `tests/*.py` che eseguono il TypeScript vero con node), non un runner
dedicato. Materiale preparatorio: `DOCUMENTAZIONE/PUNTO_9_TEST_FRONTEND.md`,
`DOCUMENTAZIONE/PROMPT_PUNTO_9.md`.

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
**fa partire il deploy Vercel**: va mergiata fuori orario cliente.

Resta scoperto, e dichiarato nel docstring del test: che il *componente* passi
`risposta` e non il pool filtrato. Il componente non è testato (nessun
rendering). Mitigazione a costo zero: il parametro si chiama `risposta`, è il
primo, e nel componente non esiste più una variabile filtrata prima della
chiamata.

### Correzione al documento preparatorio

`PUNTO_9_TEST_FRONTEND.md` citava `margini.ts` come «dove sta il calcolo dei
numeri del cliente»: **falso**, contiene solo tipi e wrapper `fetch`, il calcolo
è server-side. Gran parte di `lib/` è così — la superficie di logica pura reale è
ben minore delle 3.339 righe. Corretto nel documento.

Le altre cifre del documento sono state ri-misurate e reggono tutte: 399 file,
50.891 righe, 3.339 in `lib/`, zero runner, 55 test node preesistenti.

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
