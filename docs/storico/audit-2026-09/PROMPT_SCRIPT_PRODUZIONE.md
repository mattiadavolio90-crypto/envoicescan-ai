# Prompt sessione — Punto 3 dell'audit: gli script che scrivono in produzione

> **Modello**: **Opus**. Normale sull'esecuzione: l'impianto esiste già (il
> chokepoint attribuito del Punto 2), qui si estende agli script. `ultrathink`
> solo se decidi di cambiare la forma della guardia.
> **Sforzo**: medio. Il pezzo che vale è la guardia sulle correzioni manuali,
> non la cancellazione dei monouso.
> **Documento vivo**: `DOCUMENTAZIONE/AUDIT_ULTIMO_PERIMETRO.md` (ignorato da
> git, sta su disco), sezione «Da dove riparte la prossima sessione».
> **Stato repo alla stesura**: `e3f59ff`, **coda push 0** (Punti 1 e 2 spediti
> l'08/09 mattina, CI verde, worker in produzione sul commit giusto), suite
> **13.177 verdi + 113 SQL**.

---

## ⚠️ Prima di tutto: ri-misura, non ereditare

Ogni cifra qui è misurata sul DB live e sul codice l'**08/09/2026**, non ripresa
da un documento. Ri-misurala comunque quando ci lavori: in questo progetto le
premesse dei prompt sono state smentite in **5 casi su 10**, e il prompt del
Punto 2 sbagliava **3 file su 11** (due falsi positivi e uno mancante — proprio
il più pericoloso). Ho lasciato qui sotto come ri-contarli.

```bash
python -m pytest -q -m sql           # 113 test, devono essere verdi
git log --oneline origin/main..main  # atteso: vuoto
python scripts/check_documentazione.py
```

Se i 113 non sono verdi **non è un problema dei test**: o lo snapshot è in drift
rispetto al DB live, o una migration nuova non si applica sopra. La fixture lo
dice esplicitamente nel messaggio d'errore.

---

## Cosa il Punto 2 ha lasciato in eredità, e che serve proprio qui

Il Punto 2 era **la precondizione di questo**. Da ieri esiste un modo per
scrivere `categoria` dichiarando chi sei:

| Pezzo | A cosa serve |
|---|---|
| `services/db_service.py` → `aggiorna_categoria_fatture(...)` | il chokepoint: `source`, `attore_email`, `attore_user_id`, `batch_id`. Chi non dichiara viene **segnalato, non bloccato** |
| RPC `aggiorna_categoria_fatture_attribuita` | sul DB live, `SECURITY DEFINER`, solo `service_role` |
| `tests/test_sql_registro_correzioni.py` | 9 test che **eseguono** il trigger |
| `tests/test_registro_correzioni_chokepoint.py` | 9 test sul chokepoint, provati per mutazione |

**Il vocabolario è già deciso, non re-inventarlo**: `source` dice **chi ha
eseguito** la scrittura (`worker_coda`, `correzione_cliente`, `agent_notturno`,
`admin_propagazione`, `post_upload`); `categoria_fonte` dice **quale regola ha
deciso** (`L2_locale`, `AI_alta`…). Per gli script il valore naturale è
`script_manuale`, meglio se col nome dello script dentro `batch_id`-adiacente
(un `batch_id` per esecuzione).

---

## Il problema, misurato

### a) I due script vivi possono ancora sovrascrivere una correzione del cliente

È **la stessa classe di bug del 26/08** (`ricategorizza_sede.py` che avrebbe
sovrascritto 19 correzioni manuali, trovato *per caso* leggendo il codice).

Misurato l'08/09, `grep` su entrambi i file: **nessuno dei due controlla
`categoria_fonte = 'correzione_cliente'` né `reviewed_at`** prima di scrivere.
Il `--dry-run` di default protegge dall'esecuzione distratta, non dalla logica:
con `--commit` riscrivono comunque.

Cosa c'è oggi da proteggere sul DB live:

| Misura (08/09) | Valore |
|---|---:|
| Righe con `categoria_fonte = 'correzione_cliente'` | **12** |
| Righe con `reviewed_at` valorizzato (riviste a mano) | **318** |
| Righe attive totali | 39.515 |

12 sono poche, ma sono **esattamente** le righe in cui un umano ha guardato e
deciso: riscriverle è il danno peggiore che questi script possano fare.

### b) Sei script scrivono `categoria` e finiscono nel registro come anonimi

Ri-misurato l'08/09 (**41 script scrittori**: 30 in `scripts/`, 11 in `tools/`):

| Script | Ultimo commit | Nota |
|---|---|---|
| `scripts/ricategorizza_sede.py` | 26/08 | **vivo** — è lo script del precedente |
| `scripts/ricategorizza_sede_ai.py` | 26/08 | **vivo** — stesso giorno, stessa classe |
| `scripts/catscan_applica.py` | 05/06 | applica correzioni da un JSON |
| `tools/fix_sospette_memoria_globale.py` | non tracciato | ⚠️ **`.update({'categoria'…}).eq('descrizione', desc)` SENZA filtro `user_id`: scrive sulle fatture di TUTTI i clienti** |
| `tools/fix_stale_cache.py` | non tracciato | per-utente |
| `tools/check_cache_prodotti.py` | non tracciato | id e liste hardcoded |

> `scripts/_recalc_review_sushiland.py` compare nei grep ma scrive solo
> `needs_review`, **non** `categoria`: falso positivo, non contarlo. Verificato
> riga per riga l'08/09.

**Come ri-contarli** (l'elenco cambia, e altre sessioni girano in parallelo):

```bash
grep -rlE "get_supabase_client|create_client" --include=*.py scripts/ tools/ | sort > /tmp/c.txt
grep -rlE "\.(update|insert|upsert|delete)\(" --include=*.py scripts/ tools/ | sort > /tmp/s.txt
comm -12 /tmp/c.txt /tmp/s.txt              # gli script scrittori
```

⚠️ `comm` **richiede input ordinato**: senza `sort` dà un numero sbagliato senza
dirtelo (mi è successo l'08/09: 9 invece di 41).

### c) I monouso che nessuno esegue ma che scrivono ancora

Dal conteggio del 07/09: **15 script monouso** di aprile-giugno, 1 commit
ciascuno, ancora eseguibili sui dati veri. **Ri-conta prima di cancellare.**

---

## Il lavoro, in ordine

### 1. La guardia sulle correzioni manuali — è la voce che vale

I due script vivi (e `catscan_applica.py`) non devono poter riscrivere una riga
che un umano ha già deciso. La domanda da porsi per ciascuno è quella del 26/08:
*«questo può sovrascrivere una correzione manuale?»*.

⚠️ **Attenzione a dove metti la guardia**, e la regola è già scritta col sangue
in questo progetto: **un vincolo giusto messo nell'hot-path del worker è una
regressione**. Qui siamo in uno script CLI lanciato a mano, quindi **bloccare è
legittimo** — al contrario del worker, dove si segnala. Ma decidilo guardando
**chi chiama**, non per analogia.

Valuta se la guardia sta meglio:
- dentro ogni script (esplicita, ma da ripetere N volte), oppure
- come parametro del chokepoint `aggiorna_categoria_fatture`
  (es. `salta_correzioni_manuali=True`), così vale anche per chi arriverà dopo.

**Misura prima di scegliere**: quante righe verrebbero saltate oggi (le 12 +
eventuali `reviewed_at`), e se saltarle silenziosamente sia accettabile o vada
stampato un riepilogo.

### 2. Far dichiarare gli script

I sei di sopra passano dal chokepoint con `source='script_manuale'` e un
`batch_id` per esecuzione. Oggi ogni loro riga finisce nel registro come
`db_trigger`, cioè **indistinguibile dal worker**: è precisamente ciò che ha reso
il precedente del 26/08 impossibile da misurare.

⚠️ `tools/` è **ignorato da git** (`.gitignore:20`): le modifiche lì non si
committano e non si spediscono. Se decidi di sistemare
`fix_sospette_memoria_globale.py` (quello senza filtro `user_id`), la scelta
«dentro o via dal repo» è **di Mattia**, non tua — chiediglielo invece di
spostarlo di iniziativa.

### 3. Il presidio

Per ciascuno script vivo, un test che **esegua lo script**, non una replica.

> `tests/test_ricategorizza_sede_pipeline.py` oggi è una **replica** del codice,
> non lo script: verde anche se lo script cambia. È il difetto da non ripetere.

**Provalo per mutazione**, o non è un presidio: backup **prima** del primo
mutante, **un mutante per volta**, e verifica col `diff` che la mutazione sia
davvero avvenuta prima di leggere il risultato (l'08/09 tre mutanti su sei non
si erano applicati e mostravano «8 passed», che non misurava niente). Controlla
anche **dentro quale funzione** cade il pattern mutato. `git status` dopo
l'ultimo ripristino.

### 4. I monouso

Ri-contali, poi cancellali. Sono codice che nessuno esegue e che può ancora
scrivere sui dati dei clienti. La convenzione dry-run diventa una riga in
`CLAUDE.md`.

---

## Vincoli da rispettare

- **Regole di dominio #1** (`Da Classificare`) e **#2** (`NOTE E DICITURE` solo
  con `totale_riga == 0`): qui si tocca di nuovo chi scrive `categoria`.
- **Il registro non copre `prodotti_utente`** (110 righe, ancora anonime): lo
  scrivono degli `upsert` che non possono impostare i GUC. Se uno script tocca
  quella tabella, **non fingere** che sia attribuito. La RPC gemella
  `aggiorna_categoria_prodotto_attribuita` è già sul live e testata, ma serve un
  upsert lato DB per usarla davvero — è lavoro suo, non un parametro in più.
- **Se applichi una migration al DB live, riallinea lo snapshot nello stesso
  commit** — e poi **ricontrolla che i test su quella migration mordano ancora**
  (neutralizza la modifica in *entrambe* le sorgenti e verifica che la suite
  vada rossa: l'08/09 ha funzionato, il 07/09 tre test erano diventati
  tautologici senza che nessuno se ne accorgesse).
- **Mai `git add -A`**: nel working tree c'è lavoro di altre sessioni (all'08/09:
  `.claude/agents/code-reviewer.md`, `.claude/settings.json`,
  `tests/test_audit_fase6_rientro_bypass.py`).
- **Push e deploy: chiedi a Mattia.** Un commit locale non deploya niente.
  Railway ridispiega anche per soli `.md`; Vercel solo se tocchi `apps/web/**`.
- **Sostituire un UPDATE con select+UPDATE introduce un limite che l'UPDATE non
  aveva.** Lezione dell'08/09: PostgREST tronca le select a **1000 righe senza
  errore**, e una sola descrizione su una sede reale è già a 930. Se lo fai, usa
  `fetch_all` (`utils/supabase_paging.py`).

## Chiusura (WORKFLOW.md §5)

Presidio provato per mutazione, commit su `main` locale, contatore
`DOCUMENTAZIONE/AUDIT_ULTIMO_PERIMETRO.md` aggiornato, `check_documentazione.py`
pulito, `/code-reviewer` verde.

> Il gate `claude_hook_reviewer_gate.py` **consuma** il marker
> `.claude/.reviewer_gate_ok` a ogni uso: se committi ancora dopo la review,
> riscatta. È il comportamento previsto, non un guasto.

Chiuso il Punto 3 **il ciclo dell'ultimo perimetro è finito**: i tre punti erano
la selezione del 07/09. Quello che resta fuori è elencato in
«Cosa NON si fa in questo ciclo, e perché» — rileggilo prima di aprire altro.

---

## Due divergenze in sospeso — sono decisioni di Mattia, non bug

Riportate il 07/09 e **non** toccate da allora. Se le riapri, ri-misurale:

- **`data_competenza` vs `data_documento`**: dashboard, chat e spreco aggregano
  per data documento; margini e gruppo per competenza. **229 righe, 3.794,14 €,
  1 sede, 1 utente** (misurato il 07/09).
- **Limite giornaliero della chat**: `chat_usage_check_and_log` usa
  `date_trunc('day', now() AT TIME ZONE 'UTC')`, quindi azzera alle **02:00
  italiane** d'estate (01:00 d'inverno). Chi chatta all'una di notte consuma la
  quota del giorno prima.
