# Stato audit ONEFLUX — ciclo 2026-08

**Ciclo nuovo, non ancora aperto.** Il ciclo precedente (2026-07) è **chiuso il
28/08/2026**: indice e storico completi in `docs/storico/`
(`AUDIT_ONEFLUX_STATO_2026-07.md` e `..._STORICO.md`).

> Il ciclo 2026-07 ha chiuso tutte e 10 le dimensioni con seconda passata e
> `code-reviewer`, più §3b/§3c (perimetro non letto) e §2 (mock globale del
> conftest). Le 36+ lezioni operative accumulate stanno nello STORICO: vale la
> pena rileggerle prima di riaprire una dimensione, perché diverse riguardano
> *come* si audita, non *cosa*.

## Da dove ripartire

Una dimensione è verde rispetto al perimetro **che quella passata si è scelta**,
non rispetto al codice esistente. È la lezione più cara del ciclo scorso: §3b e
§3c sono nate proprio dal conto onesto di quanto era stato letto davvero.

Voci ereditate dal ciclo 2026-07, da valutare quando si apre questo:

- ~~**Le 9 funzioni `@_make_cache` di `db_service`** che ignorano il client
  passato dal chiamante~~ — **VOCE RITIRATA il 28/08/2026: il difetto non
  esiste.** Verificate tutte, una per una. Era sbagliata su tre punti:
  1. **Sono 8, non 9.**
  2. **Non ignorano nessun client.** Solo 2 delle 8 accettano un parametro
     client, e l'unica reale (`get_fatture_cestino`) lo gestisce correttamente:
     `if supabase_client is None:` → fallback **solo** se non gli è stato
     passato niente. `_carica_fatture_da_supabase` era un falso positivo: la
     parola "client" compare nel docstring, non nella firma.
  3. **Il comportamento è deliberato e già documentato.** Il docstring di
     `_key_part` (`utils/streamlit_compat.py`) spiega che i client si
     identificano per TIPO e non per valore, altrimenti il repr con
     l'indirizzo di memoria cambierebbe la chiave a ogni istanza e la cache
     non colpirebbe mai. E il client è comunque un **singleton di processo**
     (`services/__init__.py:245`): non esistono due client fra cui sbagliare.

  **Il leak fra tenant — la cosa che avrebbe reso grave la voce — non si
  verifica:** tutte e 8 hanno `user_id` nella chiave di cache, e tutte quelle
  per-sede hanno anche `ristorante_id`. L'unica senza
  (`get_custom_tag_prodotti`) filtra su `tag_id` + `user_id`, entrambi in
  chiave.

  **Da dove veniva l'allarme.** Da un fatto vero ma diverso: in §2, togliendo
  il mock di supabase, `_fetch_numero_documento_map_cached` faceva una
  richiesta HTTP **vera** nei test (in locale con le credenziali di
  produzione, via `load_dotenv(override=True)`). Quello era un problema *dei
  test*, contenuto dalla guardia di rete. Da lì è stato generalizzato a "9
  funzioni ignorano il client", che non è ciò che fanno. **Lezione: una
  generalizzazione scritta a caldo va riverificata prima di diventare una voce
  di audit** — è la stessa regola del "ogni severità si riverifica", applicata
  a una voce nata dentro il ciclo invece che ereditata.

  **Cosa resta di vero, e cosa NON si è fatto.** Quelle funzioni sono difficili
  da testare senza rete: è una proprietà del design a singleton, non un difetto
  di correttezza. Il refactor (aggiungere `supabase_client=None` alle 7 che non
  ce l'hanno) è stato **valutato e scartato**: toccherebbe 7 funzioni di accesso
  dati in produzione per chiudere zero difetti, a ridosso del go-live. La regola
  adottata: aggiungere il parametro **quando serve davvero**, cioè quando si
  scrive un test per una di quelle funzioni e la guardia di rete si mette di
  traverso — una riga, su una funzione sola, giustificata dal test. È come è
  nato `get_fatture_cestino`. Se invece l'obiettivo diventa la copertura a test
  di quelle 8, va aperta come voce sua.
- **`worker/email_queue_processor.py`** scrive i ricavi giornalieri fuori dal
  router: agganciato a `_spegni_override_mensile`, ma nuovi percorsi di
  scrittura vanno agganciati anche loro (`services/routers/ricavi.py`).
- **Il canale SDI non applica la policy date**: decisione a verbale (STORICO §27
  e §32), difesa da `tests/test_upload_policy_canale_sdi.py`. Non è una svista.
- **Il flush PROP-1** prima del blocco policy: documenta-e-chiudi, refactor
  sproporzionato al rischio.
- ~~**`tests/worker_test.py` non gira mai**~~ — **CHIUSA il 28/08/2026**,
  sostituita da `tests/test_worker_endpoints.py` (5 test, 3 mutanti uccisi).
  Due precisazioni rispetto a come era annotata:
  1. Il file *era* raccoglibile nominandolo esplicitamente (`pytest
     tests/worker_test.py` → 3 test). Non veniva raccolto **in CI** perché
     `testpaths` scandisce le *directory* applicando il glob `test_*.py`, e il
     suffisso `_test.py` non matcha. La distinzione conta: "rinominare" non era
     una fix neutra.
  2. Non erano unit test ma uno **script di smoke manuale** — `requests` verso
     `localhost:8000`, `print()`, blocco `__main__`. Rinominarlo li avrebbe
     resi **rossi fissi in CI**, dove nessun worker ascolta (oggi falliscono
     sulla guardia di rete del conftest: il segnale corretto).
  Il rimpiazzo guida gli stessi 3 endpoint in-process con `TestClient` (come
  `test_worker_metrics.py`): niente socket, niente GPT. E copre una proprietà
  che lo script **non verificava affatto** — il 401 senza `X-Worker-Key`:
  girando in locale con la chiave in ambiente, quel ramo non lo vedeva mai.
  `/api/classify` e `/api/parse` non avevano **nessun** altro test nella suite.
- ~~**`ph = argon2.PasswordHasher()`** usa i default della libreria~~ —
  **CHIUSA il 28/08/2026**. Parametri ora espliciti (`m=65536, t=3, p=4`),
  asseriti da `tests/test_auth_argon2_parametri.py` (8 test, 4 mutanti uccisi).
  Precisazioni rispetto a come era annotata:
  - **Nessuna migrazione, nessun rischio per gli hash esistenti**: i parametri
    sono incorporati nell'hash (`$argon2id$v=19$m=65536,t=3,p=4$...`) e
    `verify()` li legge da lì, non dall'hasher. Verificato che un hash con
    `m=8192,t=2` resta valido. Costo di hashing invariato (~87 ms).
  - **Il rischio "cambio silenzioso" era più contenuto**: `requirements.txt` ha
    `argon2-cffi>=23.1.0` (senza tetto), ma è `requirements-lock.txt` a essere
    installato e pinna `==25.1.0`. Un cambio di default arriverebbe solo con un
    aggiornamento deliberato del lock.
  - **`p=4` non era dichiarato in CLAUDE.md**: concorre al costo come gli altri
    due ed era rimasto implicito. Ora è nel doc, e un test lo verifica in
    entrambe le direzioni (codice→doc e doc→codice).
  - Il mutante che conta è "torna a `PasswordHasher()`": i *valori* restano
    identici (i default coincidono), quindi solo
    `test_parametri_espliciti_non_ereditati_dai_default` lo uccide. È la
    differenza fra misurare la libreria e misurare il codice.

- **Migrazione Argon2→Argon2 assente** (emersa chiudendo la voce sopra, NON
  affrontata): `check_needs_rehash()` non è chiamato in nessun punto del repo.
  Oggi è innocuo — i parametri non sono mai cambiati — ma se un giorno si
  alzano, gli hash vecchi restano vecchi per sempre: `verify()` continua ad
  accettarli e nessuno li ri-hasha. Esiste già il precedente della migrazione
  SHA256→Argon2 in `verify_and_migrate_password()`, che è il posto naturale
  dove agganciarla. Tocca il percorso di login: va valutata a parte.

## Metodo (invariato, e non derogabile)

- Audit **read-only** prima di qualunque fix; remediation solo dopo conferma
  esplicita di Mattia.
- Ogni severità **si riverifica** sul DB live o eseguendo il codice. Nel ciclo
  scorso è successo **cinque volte** che un numero ereditato non reggesse alla
  riverifica — non perché il verbale fosse sbagliato, ma perché era vecchio.
- Ogni fix nuovo richiede test verificati **per mutazione, su copia in
  scratchpad**, mai sul file del branch. E attenzione a *cosa* misura il test:
  un mutante è sopravvissuto perché il test contava le righe aggiornate invece
  delle query emesse.
- `code-reviewer` sul diff cumulativo **a fine sessione, sempre**.
- Migration solo con conferma esplicita, applicata **prima** del deploy.
- Deploy solo fuori orario clienti, salvo conferma esplicita e specifica.
- CI parte su `pull_request` o push a `main`/`progetto`.
