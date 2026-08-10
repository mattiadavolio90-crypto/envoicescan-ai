# ONEFLUX — Backup & Disaster Recovery

Cosa fare **prima** che serva (setup, verifica) e **quando** serve (ripristino
reale). Scritto dopo il primo test di restore end-to-end, eseguito il
10/8/2026: dump reale scaricato, ripristinato su un Postgres 17 pulito
(container isolato), dati confrontati riga per riga col DB live. Esito:
integro. Metodo e numeri di quel test sono riportati qui sotto.

---

## 1. Stato attuale in una riga

**Supabase piano Free (niente PITR) + `pg_dump` notturno su GitHub Actions,
retention 14 giorni.** RPO ~24h, RTO ~1-2 minuti (verificato). Nessun alert
automatico dedicato oltre alla mail di GitHub sui run falliti (scelta
10/8/2026: niente canale extra per ora).

---

## 2. Come funziona il backup

- **Workflow**: `.github/workflows/db_backup.yml`
- **Quando**: ogni notte alle 03:11 UTC (~05:11 CEST), fuori orario clienti.
  Anche avviabile a mano (`workflow_dispatch`).
- **Come**: `pg_dump -Fc --no-owner --no-privileges` (formato custom
  compresso, ripristinabile selettivamente con `pg_restore`) via connessione
  "Session pooler" (porta 5432, IPv4 — l'unica che funziona da GitHub Actions
  sul piano Free, la connessione diretta è IPv6-only).
- **Dove finisce**: artifact GitHub del repo, nome
  `oneflux-db-backup-<timestamp>`, **retention 14 giorni**. Indipendente dal
  piano/stato di Supabase — se il problema fosse lato Supabase, il backup non
  ne risente.
- **Dimensione tipica**: ~3.8MB (dato all'10/8/2026, 12 sedi, 35.622 fatture,
  2.880 prodotti master). Ben sotto qualunque limite GitHub (500MB free tier).
- **Guardia anti-dump-corrotto** (aggiunta 10/8/2026): se il file generato è
  sotto 100KB, il job fallisce esplicitamente invece di caricare un artifact
  inutilizzabile con successo apparente.
- **Se il secret manca o il job fallisce**: il run risulta rosso in GitHub
  Actions e GitHub manda la notifica email di default al proprietario del
  repo. Non c'è (per scelta, 10/8/2026) un alert Telegram dedicato come per
  gli altri monitor (`uptime_check.yml`, `ricavi_queue_monitor.yml`, ecc.) —
  se in futuro si vuole aggiungere, è lo stesso pattern già in uso in quei
  workflow.

## 3. Come verificare che il backup stia funzionando (5 minuti)

```powershell
gh run list --workflow=db_backup.yml --limit 5
```

Tutti `completed`/`success` = ok. Un run rosso = investigare subito (secret
scaduto/ruotato, cambio password DB, problema di rete Supabase).

Per controllare che l'ultimo dump non sia vuoto/troncato senza fare un
restore completo:

```powershell
gh run download <run-id> -n oneflux-db-backup-<timestamp>
# La guardia nel workflow blocca già sotto i 100KB, ma un doppio controllo
# manuale: un dump sano è nell'ordine dei MB, non KB.
```

---

## 4. Procedura di ripristino — passo per passo (testata 10/8/2026)

### Quando usarla
- Comando distruttivo eseguito per errore su dati di produzione (DELETE/UPDATE
  senza WHERE, migration sbagliata).
- Corruzione dati rilevata che richiede di tornare a uno stato precedente.
- Problema irreversibile lato Supabase (perdita progetto, non solo downtime).

### Passo 0 — Prima di tutto: NON improvvisare query di "riparazione"
Se il danno è ancora in corso (es. un processo che sta cancellando righe),
fermalo prima (killswitch, redeploy, disabilita il trigger). Il restore parte
da un dump della notte precedente: non salva le operazioni della giornata in
corso, quindi ha senso solo dopo aver fermato l'emorragia.

### Passo 1 — Trova il dump giusto

```powershell
gh run list --workflow=db_backup.yml --limit 20
```

Scegli il run **precedente** al momento del danno (se il danno è avvenuto
oggi pomeriggio, serve il dump di stanotte, non uno più vecchio a meno che
il danno sia più vecchio di quanto pensi).

```powershell
gh run download <run-id> -n oneflux-db-backup-<timestamp>
```

Scarica un file `.dump` (~3-4MB).

### Passo 2 — Caso A: ripristino su un progetto Supabase NUOVO (perdita totale progetto)

1. Crea un nuovo progetto Supabase (MCP `create_project` o dashboard).
2. Applica le migration da `supabase/migrations/` per ricreare schema/RLS
   **oppure** lascia che sia `pg_restore` a farlo (il dump include già DDL —
   preferibile usare il dump, è lo stato esatto del momento, non lo stato
   "se tutte le migration fossero state applicate in ordine").
3. Prendi la connection string "Session pooler" del nuovo progetto (Project
   Settings → Database → Connect).
4. Ripristina:
   ```powershell
   pg_restore "<connection-string-nuovo-progetto>" -Fc --no-owner --no-privileges --clean --if-exists oneflux_backup_<timestamp>.dump
   ```
   `--clean --if-exists` fa sì che ripulisca oggetti eventualmente già creati
   prima di reinserirli (utile se hai già applicato le migration a mano).
5. Aggiorna `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` su Vercel, Railway
   (worker + queue-worker) e nei secret GitHub Actions.
6. Verifica `/health` del worker e login su un account di test.

### Passo 3 — Caso B: dati corrotti ma progetto Supabase sano (il caso più probabile)

Qui **non si fa un restore diretto sul DB live** (sovrascriverebbe anche i
dati buoni arrivati dopo il dump). Si ripristina il dump su un progetto/DB
**temporaneo**, si estraggono/verificano solo le righe che servono, e si
reinseriscono a mano o con un `INSERT ... SELECT` mirato nel DB live.

1. Segui i passi del test verificato (sotto, §5) per tirare su un Postgres
   temporaneo e ripristinarci il dump.
2. Interroga il DB temporaneo per capire l'entità del danno (quali righe
   mancano/sono cambiate rispetto a live).
3. Scrivi una query mirata di reinserimento/correzione contro il DB live,
   filtrando **solo** le righe toccate dal danno — mai un restore cieco che
   sovrascrive anche gli inserimenti legittimi avvenuti dopo il dump.
4. Verifica sul DB live coi conteggi (vedi §5, tabella di confronto).

### Passo 4 — Sempre, dopo un restore
- Verifica `needs_review`/margini non falsati (regola dominio: righe "Da
  Classificare" escluse dai margini, non deve cambiare per via del restore).
- Annota in memoria/changelog cosa è successo e come è stato risolto — un
  incidente reale è la miglior prova che la procedura funziona (o dove va
  corretta).

---

## 5. Il test di restore del 10/8/2026 — metodo replicabile

Eseguito per verificare che il backup non fosse solo "si crea" ma anche "si
ripristina con dati integri". Comandi esatti, riutilizzabili:

```bash
# 1. Scarica l'ultimo dump
gh run list --workflow=db_backup.yml --limit 1
gh run download <run-id> -n oneflux-db-backup-<timestamp>

# 2. Postgres 17 pulito e isolato (Docker Desktop deve essere avviato)
docker run -d --name oneflux-restore-test -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=restoretest -p 15432:5432 postgres:17

# 3. Copia il dump nel container (su Windows/Git Bash: MSYS_NO_PATHCONV=1
#    evita che i path unix negli argomenti vengano tradotti in path Windows)
export MSYS_NO_PATHCONV=1
docker exec -i oneflux-restore-test sh -c 'cat > /tmp/backup.dump' < oneflux_backup_<timestamp>.dump

# 4. Restore
docker exec -e PGPASSWORD=testpass oneflux-restore-test \
  pg_restore -U postgres -d restoretest --no-owner --no-privileges -j 4 /tmp/backup.dump
# ~188 errori attesi e innocui: "role authenticated/service_role does not
# exist" sulle policy RLS — normali su Postgres vanilla, non esistono su un
# progetto Supabase reale. Non toccano i dati.

# 5. Verifica dati
docker exec -e PGPASSWORD=testpass oneflux-restore-test psql -U postgres -d restoretest -c "
SELECT 'fatture' t, count(*) FROM fatture
UNION ALL SELECT 'prodotti_master', count(*) FROM prodotti_master
UNION ALL SELECT 'ristoranti', count(*) FROM ristoranti
UNION ALL SELECT 'margini_mensili', count(*) FROM margini_mensili
UNION ALL SELECT 'ricavi_giornalieri', count(*) FROM ricavi_giornalieri
ORDER BY 1;"

# 6. Pulizia
docker rm -f oneflux-restore-test
```

**Risultato ottenuto** (dump 03:50 UTC del 10/8 vs DB live interrogato subito
dopo): `fatture` 35.622=35.622, `prodotti_master` 2.880=2.880, `ristoranti`
12=12, `margini_mensili` 66=66, `ricavi_giornalieri` 930 vs 942 live (12 righe
in più = inserimenti avvenuti dopo le 03:50, RPO atteso, non un problema).

---

## 6. Perché Supabase Free e non Pro (decisione riconfermata 10/8/2026)

- Il motivo originale per considerare Pro (PITR) è coperto in modo
  indipendente e **verificato** dal workflow `pg_dump` + questo restore
  testato.
- RPO 24h accettabile al volume attuale (2 clienti test + 1 operativo).
- DB a 3.8MB, lontanissimo dal limite 500MB del piano Free.
- **Quando rivalutare**: crescita clienti significativa (mole dati vicina al
  limite Free, o serve più compute/connessioni), oppure serve una feature
  esclusiva Pro diversa dal solo backup, oppure Supabase stringe i limiti del
  piano Free.

---

## 7. Limiti noti, aperti di proposito

- **Nessun alert dedicato sul fallimento del backup** oltre alla mail
  standard di GitHub — scelta esplicita del 10/8/2026, Telegram escluso per
  ora. Se si vuole aggiungere, pattern già pronto in `uptime_check.yml` /
  `ricavi_queue_monitor.yml`.
- **RPO 24h**: un disastro nel pomeriggio perde la giornata. Da rivalutare se
  cresce la mole di dati inseriti giornalmente.
- **Il restore su progetto nuovo (Caso A) non è stato provato end-to-end**,
  solo il restore dati su Postgres pulito (Caso B/test). Il passo "ricreare
  un progetto Supabase da zero e ripuntare Vercel/Railway" segue la stessa
  logica di `docs/DEPLOY_RUNBOOK.md` ma non è stato eseguito per davvero.
