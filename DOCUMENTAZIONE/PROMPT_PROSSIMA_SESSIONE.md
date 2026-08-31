# Prompt per la prossima sessione

> Copia il blocco qui sotto come primo messaggio della nuova sessione.

---

Il ciclo audit corrente è `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08-29.md`;
i verbali delle sessioni chiuse stanno in `..._STORICO.md`. Il ciclo 2026-08 è
**chiuso e archiviato** in `docs/storico/`: non riaprirlo.

**Il contatore della copertura è `DOCUMENTAZIONE/AUDIT_COPERTURA.md`**
(creato il 31/8/2026): è l'unico posto dove le somme tornano, e va aggiornato a
fine sessione insieme alla roadmap. Misurato il 31/8: **19% letto
integralmente, 16% auditato per dimensione, 65% mai guardato** su 109.964
righe. «Luglio + agosto coprono tutta l'app» **è falso** — leggilo prima di
dichiarare chiuso qualsiasi perimetro.

## ⚠️ Prima di scrivere una riga: c'è lavoro in coda, non spedito

Mattia accumula più sessioni e **deploya una volta sola, la sera**. Regola
aggiornata il 31/8/2026 (`CLAUDE.md` §«Dove si lavora», `WORKFLOW.md` §0):
**si lavora su `main` locale, niente branch, niente PR.** All'inizio della
sessione:

```bash
git branch --show-current           # deve essere main
git log --oneline origin/main..main # cosa e' gia' in coda, non spedito
```

Se quel secondo comando non è vuoto, **dillo a Mattia subito**: c'è lavoro
fatto e non ancora spedito, e va saputo prima di aggiungerne altro. Se ti
trovi su un branch, torna su `main` — non impilare una sessione sull'altra.

**Non spedire senza via esplicito di Mattia**, anche a test verdi: `git push`
(e a maggior ragione `gh pr merge`) È il deploy, e ha una finestra oraria
(sera/notte/mattina presto).

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

## Cosa si fa, e cosa viene dopo

**Si finisce lo scadenziario** (blocco «opzione A» qui sotto). Poi si apre
`margini/`, non prima.

Il contatore (`AUDIT_COPERTURA.md`, 31/8) ha misurato che la tabella «perimetro
scoperto» della roadmap elenca **4 aree frontend su 14**, e non le due più
grandi — la coda vera è questa:

| Area | Righe | Stato |
|---|---:|---|
| `(app)/workspace/` | 5.012 | 🔴 mai guardata — **la più grande dell'app** |
| `(app)/margini/` | 4.795 | 🔴 mai guardata — **tocca il MOL** |
| `components/` | 7.298 | 🔴 mai guardata — condivisa da tutte le pagine |
| `(app)/scadenziario/` client | 2.210 | 🟠 il lavoro qui sotto |

**Deciso da Mattia il 31/8: si finisce lo scadenziario.** Regola sua, ora in
`WORKFLOW.md` §5bis: *una cosa alla volta, chiusa davvero prima della
successiva — niente strascichi*. Lo scadenziario è l'unica cosa aperta, quindi
si chiude quello. `margini/` (4.795, tocca il MOL) è la dimensione **dopo**, e
si apre solo a scadenziario chiuso.

**Chiuso davvero** = tutti e 5 i punti di §5bis, non tre su cinque: mutazione,
commit, verbale, contatore `AUDIT_COPERTURA.md` ri-misurato,
`check_documentazione.py` pulito.

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

## Se lo scadenziario chiude presto: NON aprire altro

Regola di Mattia (§5bis): una cosa alla volta. Se lo scadenziario chiude e
avanza tempo, **si chiude bene** — verbale, contatore ri-misurato,
`check_documentazione.py` pulito, `code-reviewer` — e la sessione finisce lì,
lasciando il prompt pronto per la successiva. Aprire `margini/` «già che ci
siamo» è esattamente lo strascico che questa regola vieta.

La coda per le sessioni successive, **per esposizione, non per dimensione**:
1. **`margini/`** 🔴 4.795 righe — tocca il MOL, regola di dominio critica.
2. **`components/`** 🔴 7.298 righe — condivisa da tutte le pagine: un difetto
   qui si moltiplica su tutte le aree.
3. **`workspace/`** 🔴 5.012 righe — la più grande, ma esposizione live bassa
   (misurata dal ciclo 07: turni 0, regole 0, ingredienti 0).
4. **`prezzi/`** 🔴 2.361 righe — 39.133 righe fattura a monte.
5. **`(mobile)/`** 🔴 3.984 righe — frontend separato, mai guardato.

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

Tre file, sempre tutti e tre:
1. **Verbale** in `AUDIT_ONEFLUX_STATO_2026-08-29_STORICO.md` (in coda, con la data).
2. **Stato** nella roadmap `AUDIT_ONEFLUX_STATO_2026-08-29.md`.
3. **Contatore** `AUDIT_COPERTURA.md` — sposta la riga (🔴 → 🔍 → 📖),
   **ri-misura le righe** coi comandi in cima al file, ricontrolla le somme.
   Senza questo passo il contatore invecchia e torna il problema che è nato per
   risolvere.

Poi **riscrivi questo prompt** per la sessione successiva: cosa è stato chiuso,
cosa resta, quale opzione è la prossima. **Committa il doc insieme al codice che
documenta** — il 30/8 il `code-reviewer` ha bloccato una chiusura perché i file
erano `git add`-ati ma mai commitati.
