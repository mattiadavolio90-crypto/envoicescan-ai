# Prompt per la prossima sessione

> Copia il blocco qui sotto come primo messaggio della nuova sessione.

---

Il ciclo audit 2026-08 è **chiuso e archiviato** (`docs/storico/`), incluse le
**8 decisioni aperte, tutte risolte il 29/8/2026** e deployate su `fb5785fd`
(PR #52 Railway + #53 Vercel, CI verde, worker `/health` ok).

Il ciclo corrente è `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08-29.md`: non ha
ancora nessuna dimensione aperta. **Resta un solo punto ereditato: F2-NOTEST.**

## Cosa c'è da fare: il punto 9 — test runner frontend

`apps/web/` non ha alcun test che **esegua** codice. L'unica rete è
`npx tsc --noEmit`, che controlla i tipi e non esegue niente.

È una **decisione presa consapevolmente**, non una svista: va affrontata come
scelta di progetto. Il materiale preparatorio è già scritto:
`DOCUMENTAZIONE/PUNTO_9_TEST_FRONTEND.md` e `DOCUMENTAZIONE/PROMPT_PUNTO_9.md`
(oggi sul branch `docs/punto-9-test-frontend`, da rebasare su `main`).

**Perché continua a costare, misurato:**

- il 29/8 una guardia su una soglia è passata da `tsc`, sembrava giusta a
  leggerla e **non scattava su nessuno dei 3 casi reali**, perché misurava dopo
  i filtri client invece che prima;
- nella stessa sessione un test scritto *apposta* per catturare un difetto di
  firma — un `grep` riga per riga — **non lo catturava**, perché il kwarg
  sbagliato stava su un'altra riga. Solo l'analisi AST l'ha visto.

Entrambi i casi sono stati trovati provando per mutazione, non leggendo.

## Cosa NON rifare

- Le 8 decisioni del ciclo 2026-08: chiuse, deployate, verbalizzate in
  `docs/storico/AUDIT_ONEFLUX_STATO_2026-08_STORICO.md` con le query che
  dimostrano ogni misura.
- Il radar anomalie: ritarato e ricollegato. **Baseline da controllare**: al
  29/8 sera `notification_inbox` aveva 0 record `source_type='radar'` su 65
  totali. Dopo i primi upload reali dovrebbero comparirne — **pochi e veri**. Se
  ne compaiono molti, la ritaratura su `numero_documento` va rivista (prima del
  fix ne avrebbe prodotti 897, tutti falsi).

## Voci aperte misurate, non ancora affrontate

Non sono sviste: sono state misurate e lasciate fuori perimetro di proposito.

1. **Il blocco notifiche `source_type='upload'` è morto** — 7 topic
   (`upload_failed`, `uncategorized_rows`, `price_alert`, `credit_note`,
   `td24_noddt`, `td24_partial`, `quality_check_failed`) in
   `upload_handler.py:1958-2130`, raggiungibili solo da `legacy_streamlit`.
   Ultima notifica emessa: **1/6/2026**. Il frontend le aspetta ancora
   (`notifiche-shared.ts:14`). Stesso meccanismo del radar, perimetro più largo:
   vanno rimappati anche gli `action_page` legacy, che oggi non producono CTA.
2. **`check_weekly`** (`anomaly_radar_service.py`) ha **zero chiamanti** e cerca
   un `price_alert` che nel percorso vivo non viene più prodotto.
3. **`normalizza_descrizione`** (5 pattern su 7) — residuo del ciclo 2026-07.

## Metodo, non derogabile

- **Ogni cifra si ri-misura al momento di scriverla**, mai ereditata da un
  documento. Nella sessione del 29/8 questo ha corretto la roadmap **quattro
  volte**, e in tre casi ha cambiato il lavoro, non solo il racconto.
- **Ogni fix si prova per mutazione**, su copia in scratchpad: si rimuove il fix
  e si controlla che i test tornino rossi. Vale **anche per un test scritto per
  correggere un test che non misurava** — è successo il 29/8.
- **Un mock che non guarda cosa gli viene chiesto non è una rete.**
- `code-reviewer` a fine di ogni gruppo, sempre.
- **Verificare che lo sha della PR sia quello inteso**
  (`gh pr view <n> --json headRefOid` contro `git log -1`) e che la CI sia verde
  **su GitHub**: gira su Python 3.12 con `requirements-lock.txt` e un gate
  `coverage --fail-under=45`, non è lo stesso segnale del verde locale.
- Migration solo con conferma esplicita, applicata **prima** del deploy.
- **Deploy fuori orario cliente**, salvo via esplicito: l'auto-deploy Railway
  parte a ogni merge su `main`, anche per un diff di soli documenti.
