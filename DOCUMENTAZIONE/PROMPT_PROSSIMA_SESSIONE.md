# Prompt per la prossima sessione

> Copia il blocco qui sotto come primo messaggio della nuova sessione.

---

Il ciclo audit corrente è `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08-29.md`;
i verbali delle sessioni chiuse stanno in `..._STORICO.md`. Il ciclo 2026-08 è
**chiuso e archiviato** in `docs/storico/`: non riaprirlo.

**Chiuso finora in questo ciclo:**
- **Dimensione «route API»** (30/8) — le 3 ipotesi di partenza erano tutte false;
  il rischio vero era strutturale ed è chiuso da
  `tests/test_route_api_auth_dichiarativa.py` (9 test, 238 endpoint enumerati
  dall'app vera, allowlist di 10 deroghe motivate).
- **Le 3 «voci aperte ereditate»** (31/8) — **2 su 3 erano false**, la terza
  aveva la domanda sbagliata. Tutte e tre chiuse, il fatto spostato dal
  documento al codice.
- **Primo pezzo di scadenziario** (31/8) — `buildCashFlow` estratta e coperta,
  4 mutanti uccisi.

## Cosa fare: continuare lo scadenziario

**È la priorità 🟠 della tabella «perimetro ancora scoperto», ed è più piccola
di come sembra.** Leggi il blocco «Perché lo scadenziario subito dopo» nella
roadmap prima di iniziare: contiene la copertura già esistente misurata.

In sintesi, **già coperto** (69 + 8 test verdi, misurati il 31/8): tutto il
backend (`get_documenti_scadenziario`, RPC aggregata, regole, catena, chat) e
**tutte** le funzioni logiche di `lib/scadenziario.ts` — `computeKpi`,
`bucketizeDocumenti`, `parseLocalDate`, `todayLocalIso`, `buildCashFlow` — su 2
fusi. **Il difetto storico di fuso su `pagata_at` è coperto anche in lettura.**

**Scoperto**: `scadenziario-client.tsx`, **2.210 righe** di rendering, stato,
hook, filtri client.

La strada già battuta due volte (`poolSaturo`/F7 il 29/8, `buildCashFlow` il
31/8) è: **estrarre la logica pura in `lib/`, coprirla, provarla per mutazione**.
Non serve un runner di componenti — il punto 9 l'ha escluso per ragione
strutturale (`deploy-vercel.yml` scatta su `apps/web/**`: ogni merge di un test
farebbe partire un deploy di produzione).

**Prima cosa da fare, prima di estrarre qualsiasi cosa**: cercare nel componente
la logica che *decide numeri o inclusioni* — filtri che scelgono quali documenti
il cliente vede, aggregazioni, confini di data. Quella è la classe di codice che
ha già prodotto difetti veri. Il rendering puro non vale l'estrazione.

Ipotesi da verificare, non da assumere:
- **i filtri client**: un documento che l'utente si aspetta di vedere può
  sparire da una vista? (È già successo: una guardia che misurava una soglia
  *dopo* i filtri client invece che prima — vedi «Trappole» in CLAUDE.md.)
- **le tre implementazioni degli stessi confini** (`computeKpi`,
  `bucketizeDocumenti`, `buildCashFlow`) sono tenute allineate da un test: se ne
  nasce una quarta dentro il componente, va estratta o agganciata a quel test.
- **`todayLocalIso` scrive `pagata_at` in produzione**: ogni nuovo punto che
  scrive date va guardato col fuso in mente, non solo con `tsc`.

## Se lo scadenziario chiude presto

In ordine dalla tabella del perimetro scoperto:
1. **`prezzi/`** 🟠 — 2.361 righe su 5 tab, **39.133 righe fattura** a monte.
2. **`admin/`** 🟡 — 3.685 righe, solo staff.
3. **`assistenza/`** ⚪ — 292 righe, `marketplace_leads` a 0.

## Voce aperta, e non è una dimenticanza

**Alzare `dependencies=[...]` a livello di `APIRouter`.** È la correzione
strutturale piena sull'auth: sposterebbe il default da aperto a chiuso **nel
codice**, non solo nel test. Non fatta di iniziativa perché tocca **238
endpoint** e cambia comportamento su tutto il traffico di 7 account veri, e
perché `_resolve_user_from_token` *restituisce* l'utente agli handler: come
dipendenza di router il suo valore non arriva all'endpoint, quindi va disegnata,
non aggiunta meccanicamente. **Va aperta come dimensione a sé, con la sua
finestra di deploy — non come appendice di un'altra sessione.**

## Baseline radar — controllala a inizio sessione, è una riga di SQL

```sql
SELECT topic_key, source_type, count(*), max(created_at)::date
FROM notification_inbox GROUP BY 1,2 ORDER BY 3 DESC;
```

Al 31/8: **0 record `source_type='radar'`**. Il radar è stato ricollegato il
29/8 — dopo i primi upload reali dovrebbero comparirne **pochi e veri**. Se sono
molti, la ritaratura su `numero_documento` va rivista: prima del fix ne avrebbe
prodotti 897, tutti falsi.

Nota misurata il 31/8: `price_alert` ha 3 righe, tutte `source_type='upload'`,
l'ultima **1/6/2026** — è la dismissione di Streamlit, non un guasto. Non
indagarla di nuovo: il perché è nel docstring di `anomaly_radar_service.py` e in
2 test di `test_radar_aggancio_percorso_vivo.py`.

## Metodo, non derogabile

- **Ogni cifra si ri-misura al momento di scriverla**, mai ereditata da un
  documento — **nemmeno da questo, nemmeno dalla roadmap**. Il 31/8 le «voci
  aperte ereditate» erano marcate «verificate ancora vere» e **2 su 3 erano
  false**: riprenderle per buone ha prodotto lavoro fantasma finché la misura
  non le ha smontate. È la quarta sessione di fila in cui succede.
- **Ogni fix si prova per mutazione**, su copia in scratchpad: si rimuove il fix
  e si controlla che i test tornino rossi. **Verifica sempre che il mutante si
  applichi davvero** prima di leggerne l'esito: un mutante che non matcha il
  sorgente «sopravvive» senza misurare niente.
- **Serve anche la controprova**: un test che diventa rosso su tutto non
  discrimina. Il 31/8 la prima stesura di un test falliva sul docstring che
  documentava il difetto — un match testuale nudo misura il proprio pattern, non
  il codice.
- **Un mock che non guarda cosa gli viene chiesto non è una rete.**
- **Leggere un `if` non dice quale suo lato è caldo.** Misura quale ramo
  percorrono i dati veri prima di dichiarare protetta una cosa.
- **`tsc` non esegue niente**: un fix può passare `tsc`, sembrare giusto a
  leggerlo e non fare nulla sui dati veri.
- Audit **read-only** prima di ogni fix; remediation solo dopo mia conferma.
- `code-reviewer` sul diff cumulativo a fine sessione, **sempre**.
- **Verifica che lo sha della PR sia quello inteso**
  (`gh pr view <n> --json headRefOid` contro `git log -1`) e la CI verde **su
  GitHub**, non solo in locale: gira su Python 3.12 con `requirements-lock.txt`
  e un gate `coverage --fail-under=45`.
- Migration solo con mia conferma esplicita, applicata **prima** del deploy.
- **Deploy fuori orario cliente**, salvo mio via esplicito: l'auto-deploy Railway
  parte a ogni merge su `main`, anche per un diff di soli documenti. Un merge
  che tocca `apps/web/**` fa partire **anche** Vercel.

## Chiusura

Verbale in `AUDIT_ONEFLUX_STATO_2026-08-29_STORICO.md` (in coda, con la data),
e aggiorna lo stato nella roadmap. **Committa il doc insieme al codice che
documenta** — il 30/8 il `code-reviewer` ha bloccato una chiusura perché i file
erano `git add`-ati ma mai commitati.
