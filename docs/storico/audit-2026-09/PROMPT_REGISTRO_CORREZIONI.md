# Prompt sessione — Punto 2 dell'audit: il registro che non sa chi ha scritto

> **Modello**: **Opus**. `ultrathink` sull'apertura (è una decisione di dominio:
> *cosa* deve dichiarare uno scrittore), normale sull'esecuzione.
> **Sforzo**: medio. Il pezzo che vale è far dichiarare gli scrittori, non il test.
> **Documento vivo**: `DOCUMENTAZIONE/AUDIT_ULTIMO_PERIMETRO.md` (ignorato da git,
> sta su disco), sezione «Da dove riparte la prossima sessione».
> **Stato repo alla stesura**: `9a74f8f`, **coda push 0** (tutto spedito il
> 07/09 sera, CI verde, worker in produzione sul commit giusto), suite **13.040
> verdi + 104 test SQL**. Ri-verificato l'**08/09/2026**: 104 SQL ancora verdi,
> coda ancora vuota, nessun commit nuovo da altre sessioni, e il fix del 07/09
> regge sul DB live (una sola variante di `get_distinct_files`, chiusa ad `anon`).

---

## ⚠️ Prima di tutto: ri-misura, non ereditare

Ogni cifra qui è misurata sul DB live e non ripresa da un documento: presa il
**07/09/2026 sera** e **ri-misurata l'08/09** — le quattro del registro sono
invariate (4.132 righe, 0 attori su ogni colonna, ultima riga 03/09).
Ri-misurala comunque quando ci lavori: in questo progetto le premesse dei prompt
sono state smentite in 5 casi su 10, e nella sessione che ha scritto questo file
il prompt precedente dava per morta una funzione che **aveva due chiamanti in
produzione** — cancellarla in blocco avrebbe rotto la cancellazione massiva.

La regola che ne esce: **provare eseguendo**. Ora si può davvero, anche sull'SQL.

```bash
python -m pytest -q -m sql           # 104 test, devono essere verdi
git log --oneline origin/main..main  # atteso: vuoto
python scripts/check_documentazione.py
```

Se i 104 non sono verdi **non è un problema dei test**: o lo snapshot è in drift
rispetto al DB live, o una migration nuova non si applica sopra. La fixture lo
dice esplicitamente nel messaggio d'errore.

---

## Cosa c'è già, e che il Punto 1 ha lasciato in eredità

| Pezzo | A cosa serve |
|---|---|
| `tests/conftest_sql.py` | Postgres locale effimero + `supabase/schema_snapshot.sql`. Fixture: `sql`, `scalare`, `db_sql` |
| `tests/test_sql_funzioni_soldi.py` | **il modello da imitare**: semina righe vere, chiama, asserisce sul risultato |
| `tests/test_sql_rpc_non_ambigue.py` | contiene un test che **prova sé stesso** ricreando il difetto in transazione |
| `supabase/schema_snapshot.sql` | allineato al live al 07/09 sera |

**Novità che serve proprio qui**: i trigger si possono ora **eseguire** nei test.
`fn_log_category_change` è un trigger, quindi si prova scrivendo su `fatture` e
leggendo `category_change_log` — esattamente come
`test_ricavi_il_trigger_aggrega_il_mese` fa in `test_sql_funzioni_soldi.py`.

> **Due trappole imparate il 07/09, che valgono qui.**
> 1. **Mai asserire sul testo del corpo** (`pg_get_functiondef`): un mutante che
>    cambia il comportamento lascia il testo intatto e sopravvive.
> 2. **Dopo aver riallineato lo snapshot, ricontrolla che i test mordano ancora.**
>    Il 07/09 il riallineamento ha reso *tautologici* tre test: erano verdi anche
>    se il presidio non funzionava. Scoperto neutralizzando la migration.

---

## Il problema, misurato

`category_change_log` dovrebbe dire **chi** ha cambiato una categoria: il
cliente, l'AI, o uno script. Misurato il **07/09/2026 sul DB live**:

| Misura | Valore |
|---|---:|
| Righe | **4.132** (dal 29/04 al 03/09) |
| con `actor_email` | **0** |
| con `actor_user_id` | **0** |
| con `batch_id` | **0** |
| `source` diverso da `db_trigger` | **0** (un solo valore distinto) |

**Perché.** Il trigger `fn_log_category_change`
(`supabase/schema_snapshot.sql:3270`) è scritto bene e aspetta i dati: legge
`request.jwt.claim.sub`, `request.jwt.claim.email`, `app.category_change_source`
e `app.category_change_batch_id`. Ma:

- i primi due **non ci sono mai**: l'auth è custom, `auth.uid()` è sempre NULL;
- gli altri due **nessuno li imposta**. Verificato col grep su `services/`,
  `worker/`, `scripts/`, `supabase/functions/`, `apps/web/src/`: **zero
  occorrenze** di `category_change_source` fuori dalle migration.

Le colonne esistono, il trigger le cerca, nessuno gliele ha mai date. Il trigger
è attivo su **due** tabelle (`schema_snapshot.sql:3594` e `:3605`):
`fatture` e `prodotti_utente` — non dimenticare la seconda.

### Il danno che quel registro doveva rendere visibile esiste già

Ri-misurato il 07/09: **34 fatture** riviste a mano (`reviewed_at` valorizzato)
sono state ricategorizzate **dopo** la revisione, in **38 eventi**, fra il
30/04 e il 27/08. Da chi, il registro non lo sa.

Il precedente del 26/08 — `scripts/ricategorizza_sede.py` che avrebbe
sovrascritto 19 correzioni manuali — fu trovato **per caso**, leggendo il codice.
Con il registro funzionante si sarebbe *misurato*.

---

## Il lavoro, in ordine

### 1. Decidere cosa deve dichiarare uno scrittore — è la parte da `ultrathink`

Non è una scelta tecnica: è la domanda «quando fra sei mesi una categoria risulta
cambiata, cosa devo poter leggere per sapere se è stato un errore?». Almeno:
**chi** (utente o script, con un nome), **cosa** (una singola correzione o un
lotto, quindi `batch_id`), **perché** (`source`: correzione manuale, AI, script,
riparto…). Deciso questo, il resto è esecuzione.

⚠️ **Il trigger legge dei GUC di sessione** (`current_setting`), e questo è il
punto tecnico che decide la forma di tutta la fase. **Misurato l'08/09, e la
strada apparentemente ovvia è una trappola già pagata da questo progetto.**

Il client Supabase è un **singleton per processo**
(`services/__init__.py:205`, `@lru_cache(maxsize=1)`, ~300 call site). Quindi:

- Passare l'attore **negli header del client** significa scrivere su un oggetto
  **condiviso da tutte le richieste**. Non è teoria: `_riallinea_auth_header`
  (`services/__init__.py:220`) esiste proprio perché è già successo — un
  `sign_in_with_password` lasciò il JWT dell'utente negli header del singleton e
  *tutte* le query successive girarono come `authenticated`, con sintomo
  «permission denied for table sessioni» subito dopo un login riuscito. La
  docstring lo racconta per esteso: **leggila prima di progettare qualsiasi cosa.**
- Con più richieste in volo, la stessa meccanica attribuirebbe la scrittura
  **all'utente sbagliato** — e un registro che attribuisce male è peggio di uno
  vuoto, perché sembra affidabile.

Quindi **non** replicare quel meccanismo. Le due strade da pesare, misurandole:

1. **Gli scrittori popolano le colonne esplicitamente** invece di affidarsi ai
   GUC. Il trigger resta com'è (già fa `COALESCE` su `'db_trigger'`), e chi
   scrive passa l'attore come dato. Più righe da toccare, ma nessuno stato
   condiviso.
2. **Una connessione dedicata** per le scritture che devono essere attribuite,
   dove `SET LOCAL` è sicuro perché la connessione non è condivisa. Da verificare
   se supabase-py lo consente senza rompere il singleton.

**Provale eseguendo prima di scegliere.** Nessuno oggi scrive
`category_change_log` a mano (verificato: solo `scripts/audit_category_change_log.py`
lo *legge*), quindi non c'è un precedente da imitare — la decisione è aperta.

### 2. Far dichiarare gli scrittori — è la voce che vale

**11 file** scrivono `categoria` con `update`/`upsert` (misurato il 07/09):

```
services/invoice_service.py      services/routers/gruppo.py
services/fastapi_worker.py       services/routers/fatture.py
worker/queue_processor.py        services/routers/admin.py
scripts/catscan_applica.py       services/routers/riparto.py
scripts/ricategorizza_sede.py    services/routers/workspace.py
scripts/ricategorizza_sede_ai.py
```

Ri-misura la lista prima di lavorarci: il codice cambia, e altre sessioni girano
in parallelo.

⚠️ **Attenzione a dove metti la guardia.** Un vincolo giusto messo nell'hot-path
del worker è una regressione: lì si **segnala**, non si blocca. Il posto giusto
si decide guardando **chi chiama**.

### 3. Il presidio

Un test che prova che **senza dichiarazione la scrittura si vede**: scrive una
categoria senza dichiarare nulla e verifica che il registro la marchi come
anonima — non che *fallisca*, ma che sia **riconoscibile**. Poi un test per
ciascuna forma di dichiarazione.

**Provalo per mutazione**, o non è un presidio: backup **prima** del primo
mutante, **un mutante per volta**, verifica che il pattern esista davvero nel
sorgente e **dentro quale funzione cade** (lo stesso pattern vive in più
funzioni: il 07/09 un mutante è risultato «sopravvissuto» solo perché aveva
mutato la funzione sbagliata). `git status` dopo l'ultimo ripristino.

### 4. Ri-misurare i 34 casi

Con il registro funzionante, quei 38 eventi vanno riletti: quali erano
legittimi e quali no. **È la domanda che ha aperto il Punto 2**, e chiuderlo
senza rispondere significa lasciarlo aperto.

---

## Vincoli da rispettare

- **Il buco di sicurezza del 07/09 è chiuso, non riaprirlo.** Ogni migration che
  crea o ricrea una funzione deve revocare **nominando i ruoli**:
  `REVOKE ALL ON FUNCTION ... FROM PUBLIC, anon, authenticated;` più il `GRANT`
  esplicito a `service_role`. Il solo `FROM PUBLIC` **non basta**: le default
  privileges del progetto danno grant nominali. Presidio:
  `tests/test_sql_funzioni_permessi.py`.
- **Se applichi una migration al DB live, riallinea lo snapshot nello stesso
  commit** — e poi **ricontrolla che i test su quella migration mordano ancora**.
- **Mai `git add -A`**: nel working tree c'è lavoro di altre sessioni.
- **Push e deploy: chiedi a Mattia.** Un commit locale non deploya niente. Railway
  ridispiega anche per soli `.md`; Vercel solo se tocchi `apps/web/**`.
- Regole di dominio **#1** (`Da Classificare`) e **#2** (`NOTE E DICITURE`): qui
  si tocca proprio chi scrive `categoria`.

## Chiusura (WORKFLOW.md §5)

Presidio provato per mutazione, commit su `main` locale, contatore
`DOCUMENTAZIONE/AUDIT_ULTIMO_PERIMETRO.md` aggiornato, `check_documentazione.py`
pulito, `/code-reviewer` verde. Chiuso il Punto 2 si passa al **Punto 3** (gli
script che scrivono in produzione: 8 vivi da leggere, 15 monouso da cancellare),
descritto nello stesso documento — di cui il Punto 2 è la **precondizione**.

---

## Due divergenze in sospeso — sono decisioni di Mattia, non bug

Riportate il 07/09 e **non** toccate. Se le riapri, ri-misurale:

- **`data_competenza` vs `data_documento`**: dashboard, chat e spreco aggregano
  per data documento; margini e gruppo per competenza. **229 righe, 3.794,14 €,
  1 sede, 1 utente** (misurato il 07/09).
- **Limite giornaliero della chat**: `chat_usage_check_and_log` usa
  `date_trunc('day', now() AT TIME ZONE 'UTC')`, quindi azzera alle **02:00
  italiane** d'estate (01:00 d'inverno). Chi chatta all'una di notte consuma la
  quota del giorno prima.
