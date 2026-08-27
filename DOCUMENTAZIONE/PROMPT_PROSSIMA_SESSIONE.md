# Prompt prossima sessione — §2: smontare il mock globale di `tests/conftest.py`

Contesto da leggere prima (5 minuti): `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07.md`
(indice) e `..._STORICO.md §32`. Questa è **l'unica voce che tiene aperto il
ciclo audit 2026-07**: tutto il resto (§1, §3b, §3c, i 4 punti §27, il MEDIUM
note di credito) è chiuso e in produzione.

## Il mandato

`tests/conftest.py:11-35` sostituisce con `MagicMock()` una lista di moduli, con
la motivazione "moduli che richiedono l'app runtime […] non disponibili
nell'ambiente test puro". **Quella premessa oggi è falsa per 8 moduli su 9.**

Conseguenza: i test sui rami `except` sono **vacui**. Un attributo di un
MagicMock non eredita da `BaseException`, quindi `except openai.RateLimitError`
solleva `TypeError` invece di catturare — e siccome `RETRIABLE_ERRORS_PARSING`
(`services/ai_service.py:276-282`) è una tupla valutata da sinistra a destra,
nemmeno il `ValueError` finale, che è una classe **vera**, viene raggiunto. Il
codice di produzione è corretto; è l'ambiente di test che mente.

**Obiettivo:** ridurre `_MODULI_DA_MOCKARE` al solo `streamlit` e sistemare le
ricadute.

## Misure già fatte (27/8/2026) — parti da qui, non rifarle

Misurato smontando un modulo per volta sulla suite completa (11.281 test), con
ripristino del conftest dopo ogni giro. **Il costo reale è molto più basso di
quanto i verbali precedenti stimassero: 10 test da sistemare, non 11.281.**

| Modulo | Installato? | Suite dopo la rimozione |
|---|---|---|
| `streamlit` | **NO** | — **resta mockato**, è l'unico mock legittimo |
| `xmltodict` | sì | ✅ 11.238 passed — **costo zero** |
| `requests` | sì | ✅ 11.238 passed — **costo zero** |
| `postgrest` | sì | ✅ 11.238 passed — **costo zero** |
| `fitz` (PyMuPDF) | sì | ✅ 11.238 passed — **costo zero** |
| `argon2` | sì | 2 failed (`test_auth_service.py::TestVerifyAndMigratePassword`) |
| `openai` | sì | 1 failed (`test_eccezioni_moduli_mockati.py`, **atteso**) |
| `tenacity` | sì | 4 errors (`test_ai_service_troncamento.py`) |
| `supabase` (+`.lib`, `._sync`) | sì | ⚠️ **122 errors** da solo — vedi sotto |

### Il caso `supabase`: 122 errori, ma non è colpa sua

Da solo dà `ModuleNotFoundError: No module named 'requests.auth'; 'requests' is
not a package` — il `supabase` **vero** importa `requests.auth`, ma `requests`
è ancora un MagicMock, che non è un package e non ha sottomoduli.

**Verificato:** smontando `supabase` + `postgrest` + `requests` **insieme**, i
122 errori diventano **3 failed**. Il cluster va tolto in un colpo solo. Non
perdere tempo a debuggare `supabase` isolatamente: è un artefatto dell'ordine.

### Stato finale misurato (solo `streamlit` mockato)

`6 failed, 11.228 passed, 43 skipped, 4 errors` — **10 test in tutto**:

| Test | Perché cade |
|---|---|
| `test_auth_service.py::TestVerifyAndMigratePassword` ×2 | Argon2 vero: hash reali, non `MagicMock`. **Non toccare i parametri** (m=65536, t=3 — CLAUDE.md §Sicurezza): adegua il test, non il codice |
| `test_eccezioni_moduli_mockati.py::test_retriable_errors_parsing_non_e_catturabile_sotto_mock` | **Rosso atteso e desiderato.** Quel file documenta il difetto: si cancella **insieme** al workaround |
| `test_db_service.py::TestCaricaScontiEOmaggi` ×2 | `db_service.py:916` — un `re` riceve un MagicMock dove ora arriva una stringa vera |
| `test_gruppo_scadenziario_fatture.py::test_gruppo_scadenziario_include_sede_tecnica` | da diagnosticare |
| `test_ai_service_troncamento.py` ×4 (errors) | `tenacity` vero: il `@retry` non è più un MagicMock passa-tutto. **Vedi la memoria `tenacity-mockato-nel-conftest`** |

## Ordine consigliato

1. **I quattro a costo zero** — `xmltodict`, `requests`+`postgrest`+`supabase`
   (insieme, vedi sopra), `fitz`. Verde al primo colpo, riduce la lista a 3.
2. **`argon2`** — 2 test, isolati.
3. **`tenacity`** — 4 errors. Il più insidioso: i test sul `@retry` finora
   misuravano il MagicMock, non la libreria. Aspettati che qualcuno fosse verde
   **per il motivo sbagliato**.
4. **`openai`** per ultimo, insieme alla cancellazione di
   `tests/test_eccezioni_moduli_mockati.py` (tutti e 4 i test lì dentro esistono
   solo per documentare il difetto che stai togliendo).
5. Ripulisci gli **unmock artigianali** ora inutili: `test_ai_deadline_retry.py:32-46`
   (tenacity), `test_auth_service.py:395-403` (requests), `test_invoice_service.py:337,461`
   (xmltodict). Sono lo stesso workaround replicato a mano.
6. Aggiorna il commento-premessa in cima al conftest: dopo il lavoro, l'unica
   motivazione vera è "`streamlit` non è installato — vedi `services/_streamlit_shim.py`".

## Trappole note

- **`importlib.reload`** (già costata il tentativo del 25/8, STORICO §23):
  ricaricare `ai_service` **ricrea** le classi di eccezione, mentre chi le ha
  catturate all'import tiene le vecchie — un `except` che non matcha più.
  Oggi l'unico consumatore esterno è `services/fastapi_worker.py:3673`
  (import locale dentro la funzione, quindi *non* esposto). Verifica prima di
  reintrodurre reload da qualche parte.
- **`tests/test_conftest_cache_guardia.py`** confronta `CACHE_WORKER` con le
  cache realmente presenti nei moduli: se il de-mocking cambia cosa è
  importabile, quella guardia parla. Ascoltala, non aggirarla.
- **`legacy_streamlit/conftest.py`** esiste ed è separato: non è nel perimetro.
- I test che fanno `patch.dict(sys.modules, ...)` in `test_worker_run.py`
  mockano `streamlit` di proposito — quelli restano.

## Metodo (non derogabile)

- Audit **read-only** prima di qualunque fix; remediation solo dopo conferma
  esplicita di Mattia.
- Ogni severità dell'agente **si riverifica** sul DB live (Supabase MCP) o
  eseguendo il codice. In questo ciclo è successo **cinque volte** che un numero
  ereditato non reggesse alla riverifica — l'ultima il 27/8: 236,23 € su 3 righe
  erano diventati 285,50 € su 7, perché il verbale era vecchio, non sbagliato.
  (La tabella qui sopra è misurata il 27/8: se il venv è cambiato, rimisura.)
- Ogni fix nuovo richiede test verificati **per mutazione, su copia in
  scratchpad**, mai sul file del branch di lavoro. E attenzione a *cosa* misura
  il test: il 27/8 un mutante è sopravvissuto perché il test contava le righe
  aggiornate invece delle query emesse — verde per il motivo sbagliato.
- `code-reviewer` sul diff cumulativo **a fine sessione, sempre**.
- Migration solo con conferma esplicita, applicata **prima** del deploy.
  (§2 non dovrebbe richiederne: è solo test.)
- CI parte solo su `pull_request` o push a `main`/`progetto` — un branch pushato
  da solo non attiva nulla. `gh` è autenticato: push, `gh pr create` e
  `gh pr merge` sono utilizzabili direttamente.
- Deploy solo fuori orario clienti, salvo conferma esplicita e specifica.
- Aggiorna indice e STORICO a fine sessione, sezione nuova numerata (prossima: §33).

## Quando §2 sarà chiusa

Il ciclo si dichiara chiuso: aggiungere "**Ciclo chiuso il gg/mm/aaaa**" in cima
all'indice, spostare indice e STORICO in `docs/storico/`, e creare
`AUDIT_ONEFLUX_STATO_<AAAA-MM>.md` per il ciclo nuovo (non riusare questo file).

## Annotazioni lasciate dal 27/8 (non §2, ma da non perdere)

- `worker/email_queue_processor.py` scrive i ricavi giornalieri **fuori dal
  router**: è stato agganciato a `_spegni_override_mensile`, ma se nascono altri
  percorsi di scrittura vanno agganciati anche loro
  (`services/routers/ricavi.py::_spegni_override_mensile`).
- Il canale SDI **non** applica la policy date: decisione a verbale (STORICO §27
  e §32), difesa da `tests/test_upload_policy_canale_sdi.py`.
- Il flush PROP-1 prima del blocco policy è **documenta-e-chiudi**, non
  dimenticato: nessun dato sbagliato, refactor sproporzionato al rischio.
