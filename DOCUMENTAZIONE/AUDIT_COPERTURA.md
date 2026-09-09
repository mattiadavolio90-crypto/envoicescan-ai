# Certificato di copertura — cicli di audit luglio → settembre 2026

> **A cosa serve questo file.** Fra sei mesi o un anno, quando si riaprirà la
> domanda «l'app è sana?», la risposta onesta **non** è rifare tutto da capo.
> Questo documento dice **cosa è già stato guardato, con quale metro, e a quale
> commit**: da lì si riparte **sul diff**, non sull'intero codice. È l'unico
> artefatto dei tre cicli che è pensato per essere letto da lontano nel tempo.
>
> È tracciato da git di proposito (eccezione a `*AUDIT*.md` in `.gitignore`,
> riga 84): un certificato invisibile al versionamento non certifica niente.

---

## La riga che conta

**Al commit `a82213e` del 09/09/2026** i tre cicli di audit (2026-07, 2026-08,
2026-09) sono **tutti chiusi**, e con essi l'audit di compliance legale dello
stesso giorno. Nessuna dimensione resta aperta. Da qui vale la regola ordinaria:
*quando tocchi un file, lo copri*.

| | |
|---|---|
| Commit certificato | `a82213e24effde39297993d54d8fd97c2485dc96` |
| Data | 09/09/2026 |
| Suite | 13.258 verdi, 44 skip, 0 rossi — di cui **176 su un Postgres vero** (`-m sql`) e 101 Deno |
| Copertura backend eseguita | **61%** (`services,utils,config,worker` — 24.239 stmts, 8.944 miss) |
| Perimetro backend | 57.297 righe Python |
| Logica SQL | 144 migration; **25 funzioni del DB eseguite da test** (erano 0 fino al 07/09) |

> Il commit precedentemente certificato era `13d188e` (13.237 verdi, 164 SQL,
> 143 migration, 20 funzioni). La differenza e' l'audit di compliance del
> 09/09/2026: +21 test (16 sui documenti legali, 12 sulle purge, meno quelli
> ricontati), +5 funzioni di retention eseguite davvero, +1 migration.

> **Lavoro ordinario dopo la certificazione** (non rientra nel perimetro d'audit,
> vale la regola «quando tocchi un file, lo copri»):
> - 09/09/2026, `5a88675` — l'indice di Salute della catena non divergeva piu' da
>   quello del PV: +12 test di comportamento su `_salute_indici_batch` /
>   `_completezza_dati_pv`, 4 mutanti uccisi. Suite **13.270 verdi, 44 skip**.
> - 09/09/2026 — in catena un errore non diventa piu' "tutto a posto": 7 punti
>   dove un `except` produceva il valore che significa "va bene" (compreso il
>   gate `tutto_ok`, acceso ogni mattina dalla cache segnali non ancora
>   generata). +22 test di comportamento, 13 mutanti uccisi — tre
>   **sopravvissuti al primo giro**, tutti per la stessa ragione: il presidio
>   guardava un helper mentre la riga mutata stava dentro l'endpoint. Riscritti
>   chiamando `gruppo_overview` / `gruppo_margini_coperti` /
>   `gruppo_spreco_categorie`. Misurato sul DB: su **34 snapshot su 34**
>   (2 account, 28/6 → 9/9) c'era almeno un segnale, da 4 a 28, mai zero — quindi
>   non "ogni tanto": **ogni giornata con dati, la prima apertura della pagina
>   mentiva**, fino al primo calcolo dei segnali (fra le 07:31 e le 16:21).
>   Suite **13.295 verdi, 44 skip**.
> - 09/09/2026 — il briefing non dice piu' due volte la stessa cosa. L'apertura
>   "fatture arrivate" ripeteva la voce to-do che sta due righe sotto e rimanda
>   alla stessa card (percorso template: ripetizione deterministica); in catena
>   lo stesso difetto su un altro tema, con in piu' un "qui sotto" FALSO su
>   mobile, dove la coda non esiste. +9 test, 4 mutanti uccisi, 5 test esistenti
>   ROVESCIATI (asserivano il testo duplicato). `_BRIEFING_CODE_VERSION` 21 -> 22:
>   senza bump la cache avrebbe servito la frase vecchia fino al TTL. La review
>   ha trovato una REGRESSIONE introdotta dal fix stesso (su mobile spariva
>   l'unica azione del giorno) e una mia affermazione piu' forte del vero — "la
>   card c'e' sempre" vale per la finestra temporale, non col toggle utente ne'
>   col taglio a 4 card: corrette entrambe, +3 test, 5 mutanti uccisi.
>   Suite **13.310 verdi, 44 skip**.

---

## Come si riparte fra un anno — la procedura, in ordine

Il punto di questo file è **evitare l'audit totale**. Si procede così:

### 1. Si misura il diff, non il codice

```bash
git diff --stat a82213e..HEAD -- services utils config worker apps/web/src supabase
git log --oneline a82213e..HEAD | wc -l
```

Una dimensione della tabella qui sotto si riapre **solo se il diff tocca i suoi
percorsi**. Se `supabase/migrations/` è identico, la logica SQL non va riletta:
è stata letta tutta, corpo per corpo, il 07/09/2026.

### 2. Si verifica che la rete regga ancora

```bash
python -m pytest tests/ -q                      # atteso: verde
python -m pytest -q -m sql                      # 164 su Postgres vero
python -m coverage run --source=services,utils,config,worker -m pytest tests/ -q
python -m coverage report --sort=cover          # atteso: >= 61%
```

**Se la copertura è scesa sotto il 61%**, qualcuno ha aggiunto codice senza
presidio: quello è il perimetro da guardare, ed è già la risposta alla domanda
«da dove comincio».

### 3. Si ri-misura, non si eredita

Ogni cifra di questo file era vera il 09/09/2026 e **non lo sarà più**. Vanno
ri-misurate prima di essere citate. È l'errore che questi cicli hanno commesso e
corretto più volte: un numero copiato da un documento non è una misura.

---

## Cosa è stato coperto, dimensione per dimensione

Le tre colonne che servono a decidere: **quando**, **con quale metro**, e **cosa
farebbe riaprire la dimensione**.

| Dimensione | Chiusa il | Metro usato | Si riapre se… |
|---|---|---|---|
| Security | 07-08/2026 | 10 dimensioni del ciclo 07; auth, upload, open redirect, RLS | cambia `auth_service.py`, l'upload, o si introduce Supabase Auth |
| Bug / Qualità / Architettura | 07/2026 | lettura completa + `code-reviewer` per fase | refactor strutturale di `services/` |
| Performance | 07/2026 | query, indici, N+1 | rallentamenti misurati in produzione |
| AI / pipeline categorizzazione | 07-08/2026 | prompt, fallback, regole di dominio #1 e #2 | si tocca `ai_service.py` o il dizionario |
| Database (schema) | 30/07/2026 | schema, FK, orfani, indici — 9 finding | migration che cambiano struttura |
| **Database (corpi delle funzioni)** | **07-09/09/2026** | **78 corpi letti dal live** con `pg_get_functiondef`, 25 eseguiti da test | **nuove funzioni SQL, o `.rpc()` nuove** |
| Test / copertura | 09/2026 | copertura eseguita, non letta: 61% | scende sotto 61% |
| Edge Functions | 27/08/2026 | deployate v40/v13, repo avanti di 10 righe di soli commenti | si modifica `supabase/functions/` (**il deploy è manuale**) |
| DevOps / Config | 07-08/2026 | CI, secrets, runbook, backup provato il 10/08 | cambia la pipeline o il provider |
| Registro delle correzioni | 08/09/2026 | ogni scrittura su `fatture` dichiara attore, `source`, `batch_id` | nuovo scrittore di `categoria` che non passa dal chokepoint |
| Script che scrivono in produzione | 08/09/2026 | 41 censiti, 8 vivi dopo il go-live | nuovo script che scrive a DB |
| **Compliance legale (privacy, cookie, termini, GDPR)** | **09/09/2026** | documenti pubblici confrontati **col codice**, non riletti: destinatari dei dati vs host contattati, retention dichiarate vs purge esistenti, export art. 20 vs tabelle con PII | **cambia un flusso di dati verso terzi, o una dichiarazione della privacy** |

---

## Cosa NON è coperto — e resta una scelta, non una dimenticanza

Va scritto qui perché **nessun audit futuro lo riscopra come se fosse una novità**.

| Area | Misura | Perché è fuori |
|---|---|---|
| Frontend `.tsx` | 42.293 righe: rendering, hook, stato, effetti | Nessun runner npm **per scelta d'impianto**: `deploy-vercel.yml` scatta su `apps/web/**`, un runner deployerebbe a ogni test. La logica pura si estrae in `lib/` (87% presidiato) |
| 7 funzioni SQL di staff | `admin_ai_mensile`, `admin_consumi_mensili`, `admin_conteggio_fatture`, `admin_fatture_per_mese`, `get_ai_costs_summary`, `get_ai_costs_timeseries`, `get_ai_recent_operations` | Le vede solo l'owner, non i clienti; non spostano un euro sui loro numeri. Rendimento basso |
| Copertura backend oltre il 61% | 10 router su 12 a copertura parziale | Le aree grasse sono state prese e ognuna ha dato un bug vero. Oltre, il rendimento cala: si copre **quando si tocca il file** |
| 96 policy RLS | mai lette una per una | Con `auth.uid()` sempre NULL e ogni client su `service_role` (BYPASSRLS) **non filtrano nulla**: la protezione è applicativa, ed è già la dimensione Security |
| Costo del personale fermo a luglio | MOL di agosto/settembre non confrontabile | **Decisione dell'owner del 07/09/2026**: lo inseriscono i clienti (Margini → «Costo personale»), il briefing li avvisa dal 28/08 |
| Ricostruzione del DB dalle migration | 230 migration su un Postgres vuoto: **18 tabelle su 59, 171 file falliti** | Il repo **non sa ricostruire il database**. I test SQL girano sullo snapshot dello schema live (`supabase/schema_snapshot.sql`), non sulle migration. Un «Postgres in CI con le migration applicate» non è un'opzione |

---

## Il difetto che i tre cicli hanno diagnosticato — e che vale più delle cifre

> Ogni ciclo ha misurato **ciò che sapeva misurare** e ha chiamato «100%» il
> proprio perimetro. Il buco non era dentro nessuno dei tre: era **fra** i tre.
> La logica dentro il database — 8.930 righe di SQL che girano a ogni scrittura —
> non era in nessun perimetro perché nessun contatore contava i `.sql`.

Chi riaprirà un audit su questa app parta da lì: **non «ho guardato tutto?», ma
«cosa è rimasto fuori dalla domanda che ho fatto?»**. Le due domande hanno
risposte diverse, e solo la seconda trova qualcosa.

Corollario operativo, pagato caro tre volte in questi cicli: **un test verde non
prova che il codice funzioni**. `tsc --noEmit` non esegue niente; un mock
generoso resta verde sul bug (i test del radar passavano su una colonna mai
esistita); un assert sul testo del sorgente sopravvive a qualunque mutazione del
corpo. Un presidio si prova **per mutazione**, o non è un presidio.

---

## Dove sta il resto

| Serve… | Documento |
|---|---|
| I verbali dei tre cicli, per esteso | `docs/storico/AUDIT_ONEFLUX_STATO_2026-07*.md`, `..._2026-08*.md`, `AUDIT_ULTIMO_PERIMETRO_2026-09.md` |
| I prompt di lavoro del ciclo 09 | `docs/storico/audit-2026-09/` |
| Come si chiude una fase (i 5 punti) | `WORKFLOW.md` §5 |
| Dove sta cosa nel codice | `DOCUMENTAZIONE/MAPPA_TECNICA.md` |
