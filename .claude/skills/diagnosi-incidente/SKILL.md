---
name: diagnosi-incidente
description: Guida l'esecuzione del runbook incidenti ONEFLUX (worker/frontend down o lento, 5xx, coda ricavi bloccata) quando arriva un alert o un cliente segnala che l'app non va. Attivala su segnali come "è arrivato un alert", "il worker è lento", "l'app non va", "coda ricavi bloccata", "ONEFLUX è offline", o via comando esplicito /diagnosi-incidente.
---

Guida (non riscrive) la sequenza diagnostica di
`DOCUMENTAZIONE/RUNBOOK_INCIDENTI.md` — quel file resta l'unica fonte di
verità, aggiornala se scopri qualcosa di nuovo durante la diagnosi invece di
tenerlo solo qui.

## Sequenza

1. **Sempre per primo — down o solo lento?**
   ```bash
   curl -sL -o /dev/null -w "vercel: %{http_code} %{time_total}s\n" https://app.oneflux.it/login
   curl -sL -o /dev/null -w "worker: %{http_code} %{time_total}s\n" https://worker-production-a552.up.railway.app/health
   ```
   - Entrambi veloci (<1s) e 200 → probabile falso allarme, verifica comunque
     il punto 4 prima di chiudere.
   - Vercel 200 ma worker lento/errore → vai al punto 2.
   - Vercel non risponde → problema Vercel/DNS (raro), controlla Vercel
     Dashboard → Deployments.

2. **Worker lento o giù — in ordine di probabilità (quasi sempre saturazione, non crash):**
   - Crash/riavvii: `railway logs --service worker`, cerca `OOM`, `killed`,
     `SIGTERM`, `Traceback`. Se sì → `railway redeploy --service=worker --yes`,
     poi torna al punto 1.
   - Saturazione (caso più probabile): Admin → Clienti → "Salute worker"
     (`/api/admin/sistema/salute-worker`), guarda il p95 delle rotte in cima.
     Giallo/rosso su `/api/auth/me` o `/api/home/*` → threadpool sotto
     pressione, spesso perché un'operazione Admin pesante gira in
     contemporanea ai clienti. Aspetta/chiudi l'operazione pesante e
     ricontrolla dopo 1-2 minuti.
   - DB collo di bottiglia (raro): via Supabase MCP `execute_sql` o dashboard,
     ```sql
     SELECT pid, now() - query_start AS duration, state, left(query, 200)
     FROM pg_stat_activity
     WHERE state != 'idle' AND now() - query_start > interval '2 seconds'
     ORDER BY duration DESC;
     ```
     Se ci sono query bloccate a lungo, capisci quale endpoint le genera
     prima di considerare un `KILL` (con cautela).

3. **5xx / eccezioni reali:**
   ```bash
   railway logs --service worker | grep -iE "ERROR|Traceback|Exception"
   ```
   `column X does not exist` / `relation Y does not exist` → disallineamento
   schema/codice (migration non applicata o codice che punta a una colonna
   rimossa) — serve intervento su codice/migration, non un riavvio.

4. **Coda ricavi bloccata (alert dedicato):**
   ```sql
   SELECT id, email_subject, status, created_at, attempt_count, last_error
   FROM ricavi_email_queue
   WHERE status IN ('pending','processing')
   ORDER BY created_at ASC LIMIT 10;
   ```
   Causa storica nota: `queue-worker` fermo per killswitch
   `WORKER_ENABLED=0` lasciato attivo dopo un deploy.
   ```bash
   railway variables --service queue-worker | grep WORKER_ENABLED
   ```
   Deve essere `1`. Se `0` o assente → riattiva e riavvia.

5. **Dopo aver risolto — sempre:**
   - Verifica che l'alert non si ripresenti (aspetta il prossimo ciclo, 10-15 min).
   - Se il fix tocca il briefing: svuota `daily_briefing_state` della sede di
     test (`feedback_svuota_cache_briefing_dopo_deploy` in memoria).
   - Se la causa era saturazione ricorrente: valuta se potenziare Railway
     usando i dati storici del p95 come evidenza, non l'intuito.
   - Annota nel changelog/memoria se emerge una causa nuova o una soglia da
     ritarare — prima cerca comunque in `memory/project_*.md` e
     `docs/storico/` se un incidente simile è già stato diagnosticato (vedi
     WORKFLOW.md §9), potresti risparmiarti la diagnosi da zero.

## Riferimenti rapidi

| Cosa | Comando/Link |
|---|---|
| Log worker | `railway logs --service worker` |
| Log queue-worker | `railway logs --service queue-worker` |
| Riavvio worker | `railway redeploy --service=worker --yes` |
| Variabili worker | `railway variables --service worker` |
| Spia latenza | Admin → Clienti → "Salute worker" |
| DB / query live | Supabase MCP `execute_sql`, o dashboard Supabase |
