# Stato audit ONEFLUX — ciclo 2026-08

**Ciclo APERTO il 28/08/2026.** Il ciclo precedente (2026-07) è **chiuso** la
stessa data: indice e storico completi in `docs/storico/`
(`AUDIT_ONEFLUX_STATO_2026-07.md` e `..._STORICO.md`).

> Il ciclo 2026-07 ha chiuso tutte e 10 le dimensioni con seconda passata e
> `code-reviewer`, più §3b/§3c (perimetro non letto) e §2 (mock globale del
> conftest). Le 36+ lezioni operative accumulate stanno nello STORICO: vale la
> pena rileggerle prima di riaprire una dimensione, perché diverse riguardano
> *come* si audita, non *cosa*.

---

# ⚑ COME SI USA QUESTO FILE (leggere per primo)

Questo ciclo è organizzato in **fasi numerate, una per sessione**. Ogni fase è
**autosufficiente**: contiene perimetro misurato, ipotesi da verificare, criterio
di chiusura e comandi. Una sessione nuova non ha bisogno di leggere le altre fasi.

**Protocollo di ogni sessione:**

1. Apri questo file e vai alla **prima fase con stato ⚪ APERTA**.
2. Esegui **solo quella fase**. Non anticipare le successive.
3. A fine sessione: aggiorna **qui** lo stato della fase (⚪→🟢 o 🟡),
   e scrivi il verbale dettagliato in `AUDIT_ONEFLUX_STATO_2026-08_STORICO.md`
   (crearlo alla prima fase chiusa; il nome matcha l'eccezione `.gitignore`
   `!AUDIT_ONEFLUX_STATO*.md`, quindi è tracciato da git).
4. **Committa il doc insieme al codice** che documenta.

**Regole non derogabili** (ereditate, costate care — vedi §Metodo in fondo):
- Audit **read-only** prima di ogni fix; remediation solo dopo conferma di Mattia.
- **Ogni severità si riverifica sul DB live.** Nel ciclo 2026-07 è caduta **8
  volte** una severità ereditata o proposta da un agente. Non è pignoleria: è
  ciò che evita di fixare codice morto e lasciare aperto quello vivo.
- Ogni fix nuovo → test verificato **per mutazione, su copia in scratchpad**.
- `code-reviewer` sul diff cumulativo **a fine sessione, sempre**.
- Un perimetro dichiarato va **misurato**, non ricordato: nel ciclo scorso è
  risultato incompleto **4 volte** (chat 4 simboli→25; feature Tag 2 file→3;
  gli "11 file grandi" mai elencati; §3c "perimetro non letto" da 2 HIGH).

---

# 📊 IL CONTO ONESTO — misurato il 28/08/2026

Rimisurato oggi con `wc -l`, **non ereditato** dall'8/8 (i numeri erano
invecchiati: il codice è cresciuto di ~2.900 righe).

| Perimetro | Righe oggi | Lette a fondo | **Mai lette** | % scoperta |
|---|---|---|---|---|
| Python runtime (`services/`,`utils/`,`config/`,`worker/`) | 55.228 | ~40.000 | **~15.000** | 27% |
| Frontend TS/TSX (`apps/web/src/`) | 50.433 | 17.314 (25 file) | **~33.100** | **66%** |
| Edge Functions (`supabase/functions/`) | 3.554 | 3.554 | 0 | ✅ 0% |
| **TOTALE** | **109.215** | ~60.900 | **~48.300** | **44%** |

> ⚠️ **Il 17.314 del frontend è un conteggio conservativo e va letto come tale.**
> È stato ricostruito grep-ando i nomi dei `.tsx` citati nello STORICO 2026-07.
> Sei nomi sono **ambigui** (`page.tsx` esiste in 36 copie, `loading.tsx` in 9,
> `layout.tsx` in 7, `tabs-switcher.tsx` 4, `filtri-periodo.tsx` 2,
> `kpi-bar.tsx` 2): impossibile sapere *quale* istanza sia stata letta, quindi
> sono **tutte contate come non lette**. Il conteggio ottimistico darebbe 21.637.
> La differenza (4.323 righe) è il prezzo di non aver mai scritto i path completi
> nel verbale — **da qui la regola, in questo ciclo, di elencare i file per path
> assoluto e non per basename.**

**La lettura che conta non è il 44%.** Il ciclo scorso ha dimostrato **due volte**
che coverage ed esposizione live divergono: `workspace.py` era priorità 1 per
coverage e gestisce ~29 righe di dati veri; `invoice_service.py` sembrava minore
ed è il passaggio obbligato di 34.000 righe. **L'ordine delle fasi qui sotto è
deciso dall'esposizione misurata sul DB, non dalle righe.**

## Esposizione live misurata sul DB (28/08/2026, progetto `vthikmfpywilukizputn`)

| Area | Tabelle | Volume reale | Verdetto |
|---|---|---|---|
| **Catena / riparto** | `riparto_costi_catena` 156, `_quote` 438 | **€67.591,75** su 156 costi, 2 utenti, ultimo inserimento **21/8/2026** | 🔴 **VIVA e calda** |
| Upload / fatture | `upload_events` 6.917 | flusso principale | 🟠 già auditato a fondo |
| Impostazioni/account | `sessioni` 361 | 7 utenti, 12 sedi | 🟠 media |
| Dashboard/chat | `chat_usage_log` 71, `assistant_preferences` 3 | media-bassa | 🟡 |
| Agenda/notifiche | `notification_inbox` 65 | bassa | 🟡 |
| Prezzi | `prezzi_preferiti` 9 | bassa | 🟡 |
| **Workspace** | ricette 5, inventario 6, diario 2, dipendenti 1, **turni 0, ingredienti 0, note 0** | **quasi nulla** | ⚪ **bassa** |
| Assistenza | `marketplace_leads` 0 | nessuno | ⚪ nulla |
| Catena tag | `gruppo_tags` 2, `gruppo_tag_prodotti` 13 | bassa ma già fixata in §3c | 🟡 |

> **Questa misura ha già cambiato il piano una volta, il 28/8.** La prima
> proposta era partire da `personale-tab.tsx` (1.834 righe, secondo file più
> grande). Sbagliata per due motivi entrambi verificati: (a) quel file **è già
> stato letto** in §3c; (b) il suo backend `workspace.py` ha esposizione
> **quasi nulla** — turni 0, ingredienti 0. Sarebbe stata la fase più costosa
> a difendere il minor numero di dati. È la stessa trappola dell'8/8.

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

---

# 🗺️ ROADMAP — le fasi, in ordine

Legenda: ⚪ APERTA · 🔵 IN CORSO · 🟢 CHIUSA · 🟡 chiusa con residui

| Fase | Oggetto | Righe | Esposizione | Stato |
|---|---|---|---|---|
| **F1** | Frontend **catena/** — i 10 file mai letti | 3.012 | 🔴 €67.591,75 | 🟢 **CHIUSA** 28/8 |
| **F2** | Frontend **impostazioni + account + auth** | 1.942 | 🟠 362 sessioni, 7 utenti | 🟢 **CHIUSA** 28/8 |
| **F3** | Frontend **components/ condivisi** (`coda-da-assegnare`, `app-sidebar`, `sidebar`, ui/) | 7.277 | 🟠 attraversa tutto | 🟢 CHIUSA 29/08 |
| **F4** | Frontend **analisi-fatture/ + dashboard/** | 4.409 | 🟠 6.917 upload | 🟢 CHIUSA 29/08 |
| **F5** | Python — i **10 moduli mai auditati come oggetto proprio** | 3.570 | 🔴 radar anomalie spento da giugno | 🟢 **CHIUSA** 29/08 |
| **F6** | Frontend **workspace/** + **agenda/** + **assistenza/** | 6.001 | 🟡 `spese_extra` viva (€4.493) — il resto fermo | 🟢 **CHIUSA** 29/08 · 1 🟡 aperto |
| **F7** | Chiusura ciclo: voci ereditate + 2 rilievi review F1 + `code-reviewer` finale | — | — | ⚪ APERTA |

**F1 è la prima per una ragione misurata, non per intuizione** — vedi sotto.

---

## 🟢 F1 — Frontend `catena/`: i 10 file mai letti — CHIUSA 28/08/2026

**Perché prima di tutto.** È l'unico punto dove coincidono le tre condizioni che
nel ciclo scorso hanno prodotto i difetti più costosi:

1. **Backend auditato a fondo, frontend mai letto.** `riparto.py` compare **17
   volte** nello STORICO 2026-07 (chiuso in §1 il 5/8, PR #14, 2 HIGH + 2 MEDIUM
   fixati). I suoi consumatori in `catena/` non sono mai stati aperti. È
   *esattamente* l'asimmetria che ha generato i 7 HIGH di §3c.
2. **Dati veri e caldi**: €67.591,75 su 156 costi e 438 quote, un utente reale
   (`2f3f93a1-…`, **3 sedi, 88 fornitori**), scritture da gennaio ad **agosto
   2026**, ultimo inserimento **21/8/2026** — sette giorni fa. Un secondo utente
   (`51015cc8-…`, **4 sedi, 164 fornitori**) ha 1 costo / 8 quote: è il gruppo
   più grande del DB ma **quasi non usa il riparto**, e la differenza fra i due
   è essa stessa un'informazione da capire in fase (feature non scoperta? non
   utile? o un difetto che l'ha resa inutilizzabile?).
3. **78 siti di calcolo locale** misurati con grep (`reduce(`, `.map(`,
   moltiplicazioni/divisioni in `const`) sui 7 file. Il pattern-radice di §3c era
   *"il client ri-deriva localmente uno stato che il worker gli ha già mandato"*:
   qui ci sono 78 occasioni per farlo, su ripartizioni di costo fra sedi.

**Perimetro — path completi, misurati il 28/8** (niente basename, vedi la regola):

| File | Righe | Siti di calcolo locale |
|---|---|---|
| `apps/web/src/app/(app)/catena/gruppo-tag-section.tsx` | 681 | 23 |
| `apps/web/src/app/(app)/catena/sintesi-catena.tsx` | 559 | 9 |
| `apps/web/src/app/(app)/catena/finestra-costi-gruppo.tsx` | 538 | 8 |
| `apps/web/src/app/(app)/catena/finestra-margini-coperti.tsx` | 456 | 15 |
| `apps/web/src/app/(app)/catena/finestra-spesa-pv.tsx` | 259 | 13 |
| `apps/web/src/app/(app)/catena/config-assistente-catena.tsx` | 202 | 7 |
| `apps/web/src/app/(app)/catena/card-segnali.tsx` | 89 | 1 |
| `apps/web/src/app/(app)/catena/page.tsx` | 76 | 0 |
| `apps/web/src/app/(app)/catena/loading.tsx` | 28 | 2 |
| `apps/web/src/app/(app)/catena/fatture/page.tsx` | 67 | 0 |
| **Totale** | **2.955** | **78** |

> **Il perimetro era di 10 file, non 9**: `catena/fatture/page.tsx` mancava
> dall'elenco. Non compariva nel grep degli endpoint perché chiama
> `/api/gruppo/scadenziario` via `workerGet`, non via `fetch`. Alla lettura ha
> prodotto un finding (F-REDIRECT). Rimisurato a fine fase il totale è **3.012**
> righe: i fix a `spreco-categorie` di altra sessione hanno toccato il perimetro
> mentre la fase era in corso.

> `mobile-catena.tsx` e `finestra-*` citate in §3c: **`mobile-catena.tsx` è già
> letto** (§32). Le `finestra-*` NO — non compaiono nello STORICO. Verificato.

**Cosa cercare (ipotesi da confermare o smontare, non conclusioni):**

- **H1 — Ri-derivazione locale delle quote.** Il worker calcola le quote di
  riparto (`riparto_costi_catena_quote`, 438 righe). Se un `.tsx` le ricalcola
  da `importo_totale × percentuale` invece di leggerle, i due numeri divergono
  appena il backend cambia regola. **Verificare**: confrontare il valore mostrato
  con `SELECT` diretto sulle quote, per lo stesso mese e la stessa sede.
- **H2 — L'override mensile, di nuovo.** È la causa-radice che in §3c è
  ricomparsa **tre volte** (§26 dialog, §32 spegnimento + mobile). `catena/`
  mostra margini e coperti aggregati: se `finestra-margini-coperti.tsx` non
  onora `ricavi_modalita_mensile`, è lo stesso difetto da 70.095 €.
  **Verificare** con `SELECT * FROM ricavi_modalita_mensile` sulle sedi del
  gruppo dell'utente `2f3f93a1-…`.
- **H3 — Campi nuovi scartati.** §3c ha trovato `prezzo_medio_tag` corretto lato
  worker e **ignorato dal client**. `gruppo-tag-section.tsx` (681 righe, 23
  calcoli) consuma gli stessi endpoint tag: verificare che consumi
  `spesa_esclusa_mix` e `PrezzoValido`, i campi introdotti il 24/8.
- **H4 — Isolamento sede↔gruppo.** §3c ha già trovato una divergenza
  sede-singola↔catena sulle note di credito (285,50 € su 7 righe), chiusa con
  migration il 27/8. Verificare che i totali di `sintesi-catena.tsx` coincidano
  con la somma delle sedi.
- **H5 — Cap PostgREST 1000.** Rischio noto e già materializzato due volte nel
  ciclo scorso. 438 quote oggi, ma è una tabella che cresce per mese × sede.

**La superficie API della pagina, misurata** (15 endpoint, 20 `fetch`):

```
/api/account/sedi              /api/gruppo/spesa-pivot
/api/gruppo/assistant-config   /api/gruppo/spreco-categorie
/api/gruppo/costi-comuni       /api/gruppo/tag  + /tag/descrizioni + /tag/prodotti/
/api/gruppo/margini-coperti    /api/riparto/  + /riparto/manuale + /riparto/riga-categoria
/api/gruppo/scadenziario       /api/gruppo/segnali
```

> **Due agganci diretti a difetti già noti, da controllare per primi:**
> - `/api/gruppo/spesa-pivot` → è la RPC SETOF con il **cap PostgREST 1000 non
>   paginato** annotata in §1. **Rimisurato il 28/8: NON è ancora a rischio.**
>   Le 12 sedi del DB non stanno su un utente solo — il massimo per utente è
>   **4 sedi / 164 fornitori / ~302 righe di pivot stimate**, contro un cap di
>   1000. Resta latente, non attivo. *(Prima stesura di questa riga diceva
>   "oggi le sedi sono 12, la soglia potrebbe essere superata": sbagliato,
>   il pivot è per utente. Corretto con la query prima di scriverlo come
>   direttiva — è la nona volta nel progetto che un numero letto di fretta
>   avrebbe orientato male una fase.)*
> - `/api/gruppo/spreco-categorie` → è l'endpoint del **bug `2026-02-29`**
>   (HIGH fixato l'8/8 con `calendar.monthrange`). Verificare che il client
>   consumi il risultato corretto e non ricalcoli il periodo per conto suo.
>
> `/api/gruppo/tag*` (9 fetch in `gruppo-tag-section.tsx`) è la superficie dei
> fix del 24/8 — è lì che va verificata H3.

**Criterio di chiusura di F1:** i 10 file letti **riga per riga** (non grep), ogni
ipotesi H1-H5 confermata **con una query sul DB** o chiusa in negativo con la
misura che la esclude, findings elencati con severità **già riverificata**.
Nessun fix senza conferma esplicita di Mattia.

### Esito (28/08/2026)

**H1 — Ri-derivazione locale delle quote: SMONTATA.** Il client **legge**
`quota_importo` dal server (`finestra-costi-gruppo.tsx:216`), affiancato a
`quota_perc` come campo indipendente: **nessuna moltiplicazione
`importo × percentuale` esiste nei 10 file**. La premessa dei "78 siti di calcolo
locale" si è rivelata fuorviante — la gran parte è geometria SVG e scaling
heatmap, non ri-derivazione di business; le ricalcolazioni vere sono 3, tutte
legittime. *Contare le occorrenze di `.map(` non misura il rischio che si voleva
misurare: è una lezione sul metodo, non su questa fase.*

**H2 — L'override mensile: CONFERMATA, in una forma diversa da quella cercata.**
Non è il client a sbagliare: è il **criterio di completezza** lato server. La RPC
`gruppo_salute_componenti` aggrega solo `margini_mensili`, dove una sede in
modalità mensile ha `fatturato_netto = 0`. → **HIGH, attivo sui dati veri**
(dettaglio sotto).

**H3 — Campi nuovi scartati: SMONTATA.** `spesa_esclusa_mix` e `PrezzoValido` non
esistono nel perimetro né in `lib/gruppo.ts`: vivono in `tag_analytics_service.py`
e nel modulo tag **di sede**, non in catena. `prezzo_medio_tag` non esiste — il
campo è `prezzo_medio`, letto dal server su due livelli e mai ricalcolato.

**H4 — Isolamento sede↔gruppo: nessuna divergenza.**

**H5 — Cap PostgREST 1000: non attivo**, ma il limite vero è un altro: la RPC
gira con `p_limit 500` e **restituisce esattamente 500 righe** (satura), mentre
il client tronca a 60 senza dirlo. → finding F-60.

### Findings

| # | Severità | Oggetto | Esito |
|---|---|---|---|
| **H2-BIS** | 🔴 **HIGH** | La completezza dati ignora `ricavi_modalita_mensile` | **FIXATO** |
| **F-EXPORT** | 🟠 MEDIUM | L'export XLSX perde l'avvertenza "parziale" | **FIXATO** |
| **F-60** | 🟡 LOW/MED | Troncamento silenzioso a 60 candidati | **FIXATO** |
| **F-REDIRECT** | 🟡 LOW | Worker giù → redirect invece di BlockRetry | **FIXATO** |
| **F-DACLASS** | 🟡 LOW | `"Da Classificare"` hardcoded 7× su 4 file | **FIXATO** |
| **F-DRIFT** | ⚪ | 19 costi su 156: somma quote ≠ totale, max 1 cent | **aperto, a Mattia** |
| **F-CHAT** | 🟠 MEDIUM | Tool chat catena rotto (token passato come `mese`) | **FIXATO** (fuori perimetro, trovato in review) |

**H2-BIS in dettaglio.** `gruppo_salute_componenti` legge solo `margini_mensili`.
Misure sul DB live (28/8):

- OFFSIDE SPORTS PUB: `netto_rpc = 0` su **7 mesi su 7**, con **€437.898,49** di
  ricavi reali negli override.
- Sul mese 7 (la vista "Anno" di default) la RPC dava `netto = 0` per **entrambi**
  i PV, mentre `_aggrega_sedi_mensili` calcolava **~€651.336**.
- Effetto a schermo: le due sedi collassate in "dati incompleti", `livello_dati`
  degradato a `"food"` → **MOL del gruppo nascosto**, sparkline/personale/spese
  soppressi, più un messaggio che nominava la causa sbagliata ("senza costo
  personale": il personale c'era).
- Verificato anche nei segnali persistiti: lo snapshot del 28/8 conteneva due
  volte *"Mancano il fatturato"* su sedi con ricavi.

**Prova che è il pattern §3c, non un caso isolato**:
`tests/test_gruppo_aggrega_sedi.py:75-91` documenta lo **stesso** difetto già
corretto in `_aggrega_sedi_mensili` ("Bug 1: override vince sullo snapshot"). La
correzione non era mai stata propagata al percorso della completezza — quarta
ricomparsa della stessa causa-radice.

**Fix**: `_applica_override_netto` chiamato dentro `_salute_componenti_raw`, dove
il periodo è già risolto, così guariscono insieme tutti e 4 i chiamanti (overview,
margini-coperti, spreco-categorie, segnali) invece di rattoppare il solo
`_completezza_dati_pv`. 14 test nuovi, **6 mutanti su 6 uccisi**.

### Verificati e scartati (non sono findings)

- Confronto float `===` a `gruppo-tag-section.tsx:650-651`: **sicuro**, stessi valori
  dello stesso array, nessun ricalcolo intermedio.
- `cellTone` con `coperti = 0`: la guardia `v !== ex.worst` neutralizza il caso.
- Sede tecnica "Costi comuni di gruppo": correttamente esclusa da `_resolve_gruppo`
  (`.eq("sede_tecnica", False)`).

### Nota di processo

F1 è stata eseguita quando questo documento **non era su `main`**: il commit che
apre il ciclo (`4af9994`) era rimasto su un branch abbandonato mentre `main`
avanzava per altra via. I findings restano validi — derivano dal codice su `main`
e dal DB live, e sono stati riverificati sul `main` corrente — ma il verbale è
stato riscritto dopo aver recuperato la roadmap. È il motivo per cui il perimetro
qui è misurato due volte (2.955 all'apertura, 3.012 alla chiusura).

**Comandi utili:**
```bash
# i file, in ordine di rischio
wc -l "apps/web/src/app/(app)/catena/"*.tsx | sort -rn

# nessun test protegge questo perimetro (atteso: 0)
find apps/web -name '*.test.*' -o -name '*.spec.*' | grep -v node_modules | wc -l

# gli endpoint worker che alimentano la pagina
grep -rn "fetch(" "apps/web/src/app/(app)/catena/" | grep -o "/api/[a-z0-9/_-]*" | sort -u
```

---

## 🟢 F2 — Frontend impostazioni / account / auth — CHIUSA 28/08/2026

**Verbale completo** in `AUDIT_ONEFLUX_STATO_2026-08_STORICO.md`.

**Esito**: 4 findings fixati (1 HIGH, 2 MEDIUM, 1 LOW), 1 aperto a Mattia.

- 🔴 **Open redirect su `/login?next=`** — il parametro finiva tal quale in
  `window.location.href`: `//evil.com` e `javascript:` portavano fuori dominio
  **dopo un login riuscito**. Nessuna ipotesi del piano lo prevedeva; è emerso
  leggendo il consumatore invece di fidarsi del produttore (`apps/web/src/proxy.ts:93`).
- 🟠 **Cambio password fuori dalla policy GDPR** — dei tre percorsi che scrivono
  una password, solo questo si fermava a `len < 8`. Il client, intanto,
  prometteva "almeno 8 caratteri" mentre il server ne chiede 10 più le
  categorie. Ora fonte unica in `apps/web/src/lib/password-policy.ts`.
- 🟠 **Cold-start del worker slogga dalla PWA** — `(mobile)` è un route-group
  fratello di `(app)`: non eredita la distinzione "token scaduto" vs "worker
  giù". 7 pagine, 82 sessioni negli ultimi 30 giorni.
- 🟡 **`logoutSession` senza timeout** — unica chiamata worker priva di
  `AbortSignal` in tutto `lib/`: worker appeso = utente che non esce.

**Perimetro corretto rispetto al dichiarato**: non ~1.900 righe di pagine ma
**1.942** comprese route API, `lib/auth.ts`, `worker-config.ts` e `proxy.ts`.
Due difetti su quattro stanno lì, incluso l'HIGH.

**Aperto**: `F2-NOTEST` — zero infrastruttura di test frontend (già rilevato in
F1). Gli invarianti client sono per ora difesi da test Python che girano in CI.
Deciso il 28/8 di **lasciarlo aperto**: introdurre un runner è una scelta di
progetto (CI, dipendenze, manutenzione), non un fix d'audit, e non si prende a
un mese dal go-live.

**Chiusi dopo F2, prima di aprire F3** (28/8):
- `F2-VERIFY` — la route `cambia-password` non aveva test su
  `verify_and_migrate_password`: disattivandolo **81 test restavano verdi**,
  cioè si sarebbe potuta cambiare la password senza conoscere quella vecchia.
  3 test nuovi, 4 mutanti uccisi su 4.
- `F-DRIFT` (residuo di F1) — fix nel codice (`riparto_service.py`) + sanatoria
  dei 19 storici + classe `quote_non_pareggiano` in `v_riparto_incoerenze`.
  **Due ipotesi sulla causa sono cadute prima di quella giusta**, e la seconda
  era mia e sembrava misurata. Causa vera: la ricomposizione delle quote per
  sede fa riemergere i mezzi centesimi. Applicata al DB live: 19 → 0 sbilanciati,
  9 periodi su 9 quadrano. Verbale dettagliato nello STORICO.

---

## 🟢 F3 — Frontend `components/` condivisi — CHIUSA 29/08/2026

**Perimetro**: `apps/web/src/components/` — **7.277 righe in 53 file**, di cui
non letti fra gli altri:
- `apps/web/src/components/fatture/coda-da-assegnare.tsx` — **701 righe**
- `apps/web/src/components/ui/sidebar.tsx` — 723
- `apps/web/src/components/landing/landing-page.tsx` — 588
- `apps/web/src/components/nav/app-sidebar.tsx` — 447
- `apps/web/src/components/demo/screens/demo-margini.tsx` — 374

**Perché conta**: un difetto in un componente condiviso si moltiplica su ogni
pagina che lo usa. `coda-da-assegnare.tsx` tocca la **coda di assegnazione
fatture**, cioè la regola di dominio #1 (`Da Classificare`): va verificato che
non reintroduca un fallback travestito lato client.

**Nota di perimetro — SMENTITA dalla misura (29/8)**: si dava `components/ui/`
per «in larga parte shadcn generato». Non lo è: `grep -c radix-ui` sui 23 file
→ **0** (il progetto usa `@base-ui/react`), e `git log` mostra **14 commit tutti
di Mattia**. Sono codice di progetto riscritto a mano. Esclusi comunque dalla
lettura riga per riga, ma per il motivo giusto: **non fanno I/O e non toccano
dati cliente**. `demo/` + `landing/` (2.675 righe) esclusi con la stessa misura:
**zero `fetch`**.

**Esito**: 1 finding 🟡 fixato (`MobileRedirect` non scattava su `/margini`:
`startsWith("/m")` matcha per prefisso), 2 findings di presentazione/UX lasciati
come decisione. Verbale completo in `AUDIT_ONEFLUX_STATO_2026-08_STORICO.md`.

---

## 🟢 F4 — Frontend upload + dashboard — CHIUSA 29/08/2026

**Perimetro — CORRETTO alla misura (29/8)**: la roadmap elencava 5 file per
1.564 righe (e ~1.900 in tabella). Il perimetro reale è di **4.409 righe in 18
file**. Mancavano i **due file più grandi dell'area**, entrambi in
`analisi-fatture/`: `articoli-tab.tsx` (**856**) e `pivot-tab.tsx` (**744**).
Il primo è dove il cliente riclassifica le righe — regola di dominio #1 — ed è
stato toccato il 28/8: auditare i soli 5 file dichiarati l'avrebbe saltato.

**Esposizione**: 6.917 `upload_events`, **426 negli ultimi 30 giorni** (ultimo
28/8) — percorso vivo.

**Esito**: **nessun fix**, tutte le ipotesi chiuse in negativo. La validazione
magic-bytes **è** presente sul percorso vivo (`fastapi_worker.py:1892`), il
client è più stretto del server, e nessun file può finire in uno stato
invisibile. Restano 2 findings. Il 🟡 è
stato **chiuso il 29/8** (vedi sotto); resta aperto solo il 🔵.

- 🟡 **CHIUSO 29/8** — calcolo YTD duplicato fra `kpi-block.tsx` e
  `sintesi-catena.tsx`, le cui due copie **erano già divergenti** (guardia
  `punti.length < 2` interna in una, al call site nell'altra). La guardia è
  stata spostata **dentro** `MolAndamento`, come nel gemello. Provato per
  mutazione: senza guardia, 1 punto produce `d="MNaN,36.0"` (linea disegnata
  **sbagliata**, non assente) e 0 punti sollevano `TypeError`. Correzione al
  verbale F4: avevo scritto solo "crasherebbe a 0 punti" — il caso a 1 punto,
  che non crasha ma rende NaN, è il più insidioso dei due.
- 🔵 **aperto** — il commento su `ai_pending` nel worker prescrive un
  comportamento che il commit `dfdebc2` ha deliberatamente abbandonato. Verbale completo in
`AUDIT_ONEFLUX_STATO_2026-08_STORICO.md`.

---

## 🟢 F5 — Python: i moduli mai auditati come oggetto proprio — CHIUSA 29/08/2026

Verificato il 28/8: questi file **non compaiono nemmeno una volta** nello STORICO
2026-07 (`grep` sul basename, 3.386 righe di verbale).

| File | Righe | Test dedicati | Nota |
|---|---|---|---|
| `utils/formatters.py` | 691 | 1 | mai auditato |
| `utils/validation.py` | 537 | 2 | mai auditato |
| `utils/text_utils.py` | 413 | 1 | **ha una voce aperta in §3a**: `normalizza_descrizione` copre 5 pattern su 7 |
| `services/notification_inbox_service.py` | 352 | 1 | 65 righe in `notification_inbox` |
| `services/anomaly_radar_service.py` | 326 | 1 | mai auditato |
| `config/prompt_ai_potenziato.py` | 305 | — | prompt AI: tocca la regola di dominio #1 |
| `services/ai_cost_service.py` | 282 | 1 | mai auditato |
| `utils/piva_validator.py` | 224 | 1 | P.IVA = chiave del canale SDI |
| `services/personale_export_service.py` | 221 | **0** | **unico con ZERO test dedicati** |
| `services/session_service.py` | 219 | 1 | 361 sessioni live |

**Ordine consigliato dentro la fase**: `piva_validator.py` e
`prompt_ai_potenziato.py` per primi — il primo perché una P.IVA sbagliata rompe
l'aggancio SDI (già causa di incidenti reali: vedi
`docs/storico/DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md`), il secondo perché
il prompt è dove la regola #1 può essere violata senza che un test se ne accorga.

**Prima di leggere, misurare l'esposizione** di ciascuno — è la regola che ha
già invertito l'ordine due volte.

---

### Esito (29/08/2026)

**Le cifre di questa tabella erano sbagliate**: non 1.899 righe ma **3.570**, non
«4 moduli» ma **10**, e `prompt_ai_potenziato.py` ha **0 test**, non «—». Terza
volta nel ciclo che una premessa di roadmap non regge alla misura.

**3 findings, nessun fix** (sono tutti Python → fuori dalla deroga):

- 🔴 **Il radar anomalie non gira più da giugno.** `anomaly_radar_service.py` ha
  un solo chiamante, dentro la funzione Streamlit `handle_uploaded_files`, morta
  con la rimozione di Streamlit — quindi **non può girare**, ed è questa la prova.
  Le date la confermano ma non la reggono da sole: le notifiche
  `source_type='upload'` (`price_alert`, `quality_check_failed`, `credit_note`)
  si fermano **tutte** al 1/6/2026, però anche 4 topic `operativa` su 8 si
  fermano a giugno, quindi il confronto per `source_type` non è di per sé
  dimostrativo (dettaglio nel verbale). Nel frattempo sono stati fatti **3.988
  upload**. Il modulo ha un file di test che passa, su codice che non gira.
- 🟡 **`normalizza_piva` accetta P.IVA estere come italiane**: il `re.sub` toglie
  ogni lettera, non solo il prefisso `IT`, quindi `DE12345678903` → `12345678903`
  → valida. Percorsi vivi: registrazione e creazione sede da admin. Non danneggia
  nessuno oggi (le 3 P.IVA in produzione sono italiane), ma la P.IVA è la chiave
  del canale SDI.
- 🟡 **Il prompt AI contraddice la regola di dominio #1** (riga 183: «"Da
  Classificare" NON è MAI una risposta valida»). La rete a valle regge — 172
  righe in `Da Classificare`, 170 con `needs_review`, e tutte le 74 NOTE con
  `totale_riga = 0` — ma la regola vive in due posti che si contraddicono, e
  quello senza test è il prompt.

**Ipotesi chiusa in negativo**: il checksum P.IVA è **corretto**, verificato
contro l'algoritmo ufficiale su 200.000 casi con zero divergenze.

**Non letti riga per riga**: `formatters.py`, `validation.py`, `text_utils.py`,
`ai_cost_service.py`, `session_service.py`. Verbale completo in
`AUDIT_ONEFLUX_STATO_2026-08_STORICO.md`.

---

## 🟢 F6 — Frontend workspace / agenda / assistenza — CHIUSA 29/08

**Esposizione misurata: bassa o nulla.** turni_personale **0**,
ingredienti_workspace **0**, ingredienti_utente **0**, note_diario **0**,
marketplace_leads **0**, ricette 5, inventario_voci 6, diario_eventi 2,
dipendenti 1, spese_extra 16.

**Perimetro** (~3.900 righe): `workspace/spese-view.tsx` 456,
`workspace/ricetta-editor.tsx` 452, `workspace/diario-tab.tsx` 427,
`workspace/inventario-tab.tsx` 397, `workspace/inventario-aggiungi-dialog.tsx` 363,
`workspace/foodcost-tab.tsx` 336, `agenda/agenda-overview.tsx` 554,
`assistenza/marketplace.tsx` 276, più i minori.

**Questa fase è deliberatamente ULTIMA.** Il ciclo scorso ha già dimostrato su
`workspace.py` che coprire codice che nessun cliente esercita produce coverage,
non sicurezza. **Se le tabelle sono ancora vuote quando si arriva qui, l'opzione
corretta è dichiararla chiusa per assenza di esposizione** — come si è fatto per
il Vision (0 righe PDF) e per il legacy di `upload_handler.py` — non leggerla
per completezza. Rimisurare prima di decidere.

### Esito (29/08/2026)

**Rimisurato, e la decisione è cambiata.** Il perimetro non è ~3.900 righe ma
**6.001** (manca dall'elenco `personale-tab.tsx`, 1.834 righe, il file più
grande). Soprattutto: **`spese_extra` non è vuota** — 16 voci, **€4.493**, un
cliente reale, ultima **ieri**, e `margini.py:1067` la legge per i totali che il
cliente vede. Chiuderla per assenza di esposizione sarebbe stato sbagliato.

Letto il **17%** che tocca dati vivi (`spese-view.tsx` + `agenda-overview.tsx`,
1.010 righe). **Non letto l'83%** che governa tabelle vuote o ferme — dichiarato
nel verbale con il dettaglio per file, `personale-tab.tsx` in testa.

- 🔧 **Un fix sotto deroga**: `TIPO_SPESA_LABEL` esisteva in **tre grafie**, due
  delle quali nello stesso file. Il cliente vedeva `Spese Generali` a schermo e
  `Spesa Generale` nel CSV dello stesso dato. Unificato sulla costante
  condivisa; nessun numero cambia. `tsc --noEmit` EXIT 0.
- 🟡 **Un finding aperto, da decidere**: il `tipo` spesa è riderivato lato server
  **solo quando la richiesta porta la categoria**. Oggi **15 righe su 16**
  (€4.393 su €4.493, il **97,8%** del denaro) hanno `categoria IS NULL` e
  passano per il ramo scoperto. È comportamento deliberato e asserito dai test
  (retrocompatibilità voci storiche), e l'utente manipola i propri dati — ma la
  UI rende la categoria obbligatoria mentre l'API no. Fuori deroga (Python +
  rotte API): decisione di Mattia.
  **Nota di metodo**: avevo archiviato questa come «ipotesi chiusa in negativo».
  Era chiusa a metà — avevo letto il codice ma non misurato quale ramo prendono
  i dati veri. L'ha trovato il `code-reviewer`.
- ✅ **Chiuse in negativo davvero**: una categoria inventata non può finire su
  `fb` (`_valida_categoria_spesa` è una whitelist che alza 400), e
  `SPESE_GENERALI_SET` (frontend) ↔ `_tipo_da_categoria` (backend) sono in
  parità esatta.

---

## ⚪ F7 — Chiusura del ciclo

1. Riprendere le **voci ereditate** elencate sopra (SDI/policy date, flush
   PROP-1, `email_queue_processor`) e le **due aperte il 28/8**: migrazione
   Argon2→Argon2 e copertura a test delle 8 `@_make_cache`.
2. `code-reviewer` sul diff cumulativo del ciclo.
3. Aggiungere "**Ciclo chiuso il gg/mm/aaaa**" in cima a questo file.
4. Spostare questo file **e il suo STORICO** in `docs/storico/`.
5. Creare `AUDIT_ONEFLUX_STATO_<nuova data>.md` — **non riusare questo file**.

---

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
