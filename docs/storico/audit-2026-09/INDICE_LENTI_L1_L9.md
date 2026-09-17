# Le lenti trasversali L1→L9 — indice — settembre 2026

I tre cicli di audit precedenti hanno guardato l'app **per strato** (security, bug,
performance, database…). Queste otto lenti la guardano **per proprieta' che attraversa
gli strati**, e ognuna ha prodotto un artefatto che prima non esisteva.

Questo file e' l'**indice**: dice cosa ha guardato ogni lente, cosa ha trovato e dove
sta il suo artefatto. Non sostituisce i verbali — li elenca. Il registro con metro
completo e condizioni di riapertura resta `DOCUMENTAZIONE/AUDIT_COPERTURA.md`.

**Stato: tutte e 9 le lenti sono chiuse** (L9 il 17/09/2026). L1 resta *parziale*
per scelta dichiarata: le classi non refutate si chiudono leggendo il chiamante.

---

## Il quadro

| Lente | Chiusa | Cosa guarda | Difetti corretti | Artefatto |
|---|---|---|---|---|
| **L1** | 14/09 (parziale) | Sweep per classe di difetto | 2 | `CLASSI_DI_DIFETTO.md` |
| **L2** | 14/09 | Isolamento fra clienti, **eseguito** | 2 | `tests/test_isolamento_per_risorsa.py` (315) |
| **L3** | 14/09 | La produzione parla (silenzi, monitor) | 1 monitor | `MAPPA_SILENZI_2026-09-14.md` |
| **L4** | 14/09 | Esito statistico dell'AI | 1 | `scripts/audit_chi_decide_la_categoria.py` + 11 presidi |
| **L5** | 15/09 | Ciclo di vita di colonne e campi | 0 + 13 morte | `CICLO_DI_VITA_COLONNE.md` + `L5_stat_colonne_2026-09-15.csv` |
| **L6** | 15/09 | Tempo, concorrenza, dipendenze che cadono | **4** | 6 file di test (44 presidi) |
| **L7** | 15/09 | Fatture ostili in ingresso | **3** | `tests/test_importi_non_finiti_fattura_ostile.py` (286) |
| **L8** | 15/09 | Mappa cache/snapshot e ordine di deploy | 1 | `MATRICE_CACHE_2026-09-15.md` + 17 presidi |
| **L9** | 17/09 | Giornata del cliente e parita' `/m` | **4** | `GIORNATA_DEL_CLIENTE_E_PARITA_M.md` + 12 presidi |

**Totale: 18 difetti corretti**, ognuno provato per mutazione.

> Le quattro lenti senza un `.md` proprio (L2, L4, L6, L7) hanno il loro verbale
> **dentro la riga di `AUDIT_COPERTURA.md`**, che per quelle e' lunga quanto un
> documento. Sono le uniche il cui racconto vive in un solo posto — ed e' la
> ragione per cui L9, che sarebbe stata la quinta, ha un verbale suo.

---

## L1 — Sweep per classe di difetto · 14/09/2026 (parziale)

Rilevatori AST/grep su 8 classi di difetto, **707 candidati** triati per classe. La
refutazione con misura a DB e' stata fatta solo per il cap PostgREST.

**Trovato:** 2 difetti confermati e corretti, piu' il chokepoint `fetch_all` messo in
ordine (`tests/test_fetch_all_ordine_totale_chokepoint.py`, 4 presidi).

**Parziale perche':** le classi non refutate restano aperte — si chiudono leggendo il
chiamante, una per una. I residui sono elencati per `file:riga` nel verbale.

📄 `CLASSI_DI_DIFETTO.md`

---

## L2 — Isolamento fra clienti, eseguito · 14/09/2026

La domanda non era «il codice sembra isolare?» ma **«un cliente riesce a leggere i
dati di un altro?»**, provata eseguendo. 240 operazioni classificate dall'OpenAPI: le
66 con un id di risorsa chiamate con la sessione di A e gli id di B, **nei due versi**,
e sui propri id come controllo positivo; 73 GET a tenant di sessione; 8 RPC `gruppo_*`
e 2 chat — su un Postgres vero.

**Risultato: 152 chiamate cross-tenant, 0 leak, 0 scritture sull'altro.**

**2 difetti corretti:** una PATCH turno accettava un dipendente altrui; assegna-sede
rispondeva 500 invece di 404.

Il presidio e' **strutturale**: un endpoint nuovo con un id di risorsa senza ricetta fa
fallire i test da solo.

📄 `tests/test_isolamento_per_risorsa.py` (315 test, `-m sql`)

---

## L3 — La produzione parla · 14/09/2026

Battito di **60 tabelle** sul DB live in sola lettura, 13 workflow CI, i corpi dei
monitor, gli errori runtime Vercel e i log/advisor Supabase.

**Trovato:** 2 silenzi veri (cose che avrebbero dovuto parlare e tacevano) e 1 monitor
corretto.

Si ri-esegue ogni mese, o dopo un job/cron/webhook nuovo: il battito si confronta.

📄 `MAPPA_SILENZI_2026-09-14.md`

---

## L4 — Esito statistico dell'AI · 14/09/2026

**La lente in cui la misura ha rovesciato la domanda.** Si voleva misurare «quanto
sbaglia l'AI»; contando prima il traffico si e' scoperto che **l'AI decide l'1,3%**
delle righe con provenienza (4 su 309): il 94,8% e' deciso prima del modello e il 3,9%
da un umano. Misurare l'errore dell'AI avrebbe descritto **4 righe**.

**1 difetto corretto:** la correzione del cliente registrava l'attore su `fatture` e
restava **anonima** su `prodotti_utente` — 113 righe di registro senza attore.

📄 `scripts/audit_chi_decide_la_categoria.py` + 11 presidi
(`test_audit_chi_decide_la_categoria.py` 5, `test_sql_attribuzione_correzione_prodotto.py` 6)

---

## L5 — Ciclo di vita di colonne e campi · 15/09/2026

Una lettura sola di 528 file di codice + 10 Edge Function + 148 SQL, letture e
scritture separate per ognuna delle **667 colonne**, incrociate con la fotografia dei
dati live.

**Nessuna colonna letta-e-mai-scritta produce un numero sbagliato in pagina.** Le 4 che
lo sono per costruzione sono innocue (`fattore_kg` ×2, `users.session_token` ×2).

**Proposte per il drop:** 11 colonne morte + 2 tabelle. Il code-reviewer ne ha bocciate
2 del primo giro: `brand_ambigui` e' viva in `ai_service.py`, `email_rate_log` e'
presupposta da un job GDPR.

**Appendice del 16/09:** il rilevatore camminava sul **filesystem** e contava 4 script
non versionati — verde in locale, rosso in CI sullo stesso commit. Perimetro portato a
`git ls-files`. Nessun verdetto dell'audit si e' spostato.

📄 `CICLO_DI_VITA_COLONNE.md` + `L5_stat_colonne_2026-09-15.csv` + 13 presidi

---

## L6 — Tempo, concorrenza, dipendenze che cadono · 15/09/2026

Un caso **eseguito** per famiglia, con l'osservabile del cliente: ora congelata alle
00:30 del 1° del mese a Roma in quattro fusi; due `claim_batch_for_processing`
concorrenti su Postgres vero; `openai.RateLimitError` sotto il `@retry` di produzione.

**Il perimetro ri-misurato con l'AST ha smentito il grep:** 2 delle «8 letture dell'ora
senza fuso» erano commenti, e le «8 chiamate HTTP senza timeout» erano **zero** (il
kwarg stava tre righe sotto). Il timeout mancante era altrove: nel client OpenAI.

**4 difetti corretti:**
1. La policy date dell'upload decideva col **giorno UTC**.
2. I client OpenAI di classificazione erano **senza timeout** (default SDK: 600 s).
3. Il lock della coda era **del lotto ma il lavoro dell'item**.
4. Il periodo di default di Margini e Analisi fatture lo decideva **il giorno del
   server**: alle 00:30 del 1° ottobre «Mese in corso» mostrava settembre intero, KPI e
   MOL compresi.

Una verifica avversaria in sola lettura ha **smentito 2 miei rilievi** — ed erano
entrambi difetti veri.

📄 6 file di test, 44 presidi: `test_upload_policy_giorno_di_roma` (3),
`test_periodo_giorno_di_roma_frontend` (24), `test_sql_concorrenza_coda` (4, `-m sql`),
`test_ai_429_attraverso_il_retry_vero` (4), `test_openai_client_timeout` (3),
`test_worker_lock_per_item` (6)

---

## L7 — Fatture ostili in ingresso · 15/09/2026

FatturaPA avversarie **eseguite** attraverso il parser vero: importi `nan`/`inf`/
`1e400`, quantita' non finite, negativi, totali fuori scala. Il danno a valle misurato
su Postgres vero (`numeric(10,2)` **accetta NaN**, `SUM()` lo propaga) e sul formatter
del frontend (`formatEuro` → `"NaN €"`).

**3 difetti corretti:**
1. Gli importi non finiti passavano **entrambe** le copie di `_to_float_safe` e tutti i
   rami di `_to_int_safe` — `json.loads` accetta i letterali nudi `NaN`/`Infinity`.
2. Una **scrittura incompleta taciuta**: il ritorno d'errore diceva `righe: 0` con un
   chunk da 500 gia' a DB, e il tetto di 2.000 righe **tronca e prosegue** mentre la
   verifica d'integrita' certificava "OK".
3. Trovato dal controllo delle inerenze, non dalla sweep: `/api/upload/invoice`
   rispondeva `righe_salvate=0` su qualunque fallimento — e quel numero ha un
   consumatore vero in `upload-modal.tsx`.

**La domanda che chiude la lente non e' «il fix funziona» ma «il fix non rompe il
resto»:** 205 test confrontano l'implementazione **pre-fix** con l'attuale su 41 valori
di traffico vero. **0 divergenze.**

📄 `tests/test_importi_non_finiti_fattura_ostile.py` (286 test)

---

## L8 — Mappa cache/snapshot e ordine di deploy · 15/09/2026

La domanda: non «il numero e' giusto?» ma **«il numero e' giusto e il cliente vede
quello di ieri?»**. Perimetro ri-misurato con l'AST: le «126 occorrenze» del prompt
contavano variabili locali chiamate `cache` — le cache che servono davvero dati al
cliente sono **14 strutture + 11 funzioni** `@_make_cache`.

**1 difetto corretto:** `gruppo_segnali_state` ha la **stessa forma** di
`daily_briefing_state` ma **non registrava la versione della logica** — 40 righe su 40
sul DB live, zero con `code_version`. Un deploy che cambiava le soglie non si vedeva
**fino a mezzanotte di Roma**.

Corretti **entrambi i lettori**, non uno: l'endpoint ricalcola, e `_conta_segnali_cache`
ritorna **`None` e non `0`** — altrimenti il gate `tutto_ok` si accenderebbe su un
conteggio che non vale piu'.

**Ordine di deploy: nessuna rotta orfana.** I 7 «path citati e non esposti» del primo
rilevatore erano **tutti falsi positivi** — 5 per la query string, 2 perche' il
confronto saltava il livello proxy di Next.

📄 `MATRICE_CACHE_2026-09-15.md` + `tests/test_segnali_catena_snapshot_versionato.py` (17)

---

---

## L9 — La giornata del cliente e la parita' `/m` · 17/09/2026

**La lente in cui la prima misura ha corretto la premessa.** «Parita' `/m`»
suggerisce uno specchio; sono **22 pagine desktop e 7 mobile**, perche' il mobile
non e' una riduzione del desktop ma un prodotto diverso (5 tab: Home, Agenda,
Movimenti, Assistente, Profilo). Cercare «le 15 pagine mancanti» avrebbe prodotto
un elenco di non-difetti. La domanda utile: **dove il mobile dice al cliente
qualcosa di diverso, e piu' sbagliato, davanti agli stessi dati.**

**CTA morte: cercate, zero trovate.** Tutti gli `href`/`router.push` letterali
confrontati con le 36 rotte reali; le destinazioni costruite lette a mano.

**4 difetti corretti — lo stesso difetto quattro volte.** Il fix R10 del 3/9 era
arrivato al desktop e **non a `/m`**: su 6 file mobile con uno stato vuoto, 4
dicevano «Nessun incasso inserito in questo mese.» mentre il worker era giu'.
Lo stato iniziale e' `null`, quindi la frase falsa compare **all'apertura della
pagina**; il toast d'errore sparisce dopo pochi secondi e la lascia li'.

**Il mutante che conta:** il primo presidio verificava che i file *chiamassero*
`mostraGuasto`, e `setFallito(false)` al posto di `true` gli **sopravviveva** —
difetto intatto, guardia verde. Chiuso verificando le due transizioni del flag e
**l'ordine dei rami** (il guasto prima del vuoto, o e' irraggiungibile).

**2 sospetti scartati dopo verifica:** il blocco KPI che sparisce su `/m` si
comporta identico al desktop; il briefing mobile era gia' corretto.

📄 `GIORNATA_DEL_CLIENTE_E_PARITA_M.md` + 12 presidi

## Cosa si impara leggendole di fila

Cinque cose ricorrono, e sono il metodo piu' che il risultato:

1. **Il grep misura qualcosa di diverso da cio' che la frase dichiara.** L6: 2 «letture
   senza fuso» erano commenti, le «8 senza timeout» erano 0. L8: «12 decoratori» erano
   11. L5: 540 file erano 528. Ogni volta l'AST o `git ls-files` hanno dato la cifra
   vera.
2. **La misura puo' rovesciare la domanda.** L4 doveva misurare gli errori dell'AI e ha
   scoperto che l'AI decide l'1,3% delle righe.
3. **Un agente si usa per contraddire, non per moltiplicare.** In L6 il refutatore ha
   smentito 2 rilievi, ed erano difetti veri; in L8 ha corretto 2 affermazioni.
4. **Un presidio non provato per mutazione e' una supposizione.** 3 presidi su 56, in
   una fase precedente, erano finti.
5. **L'ambiente pulito misura la verita'.** Il rosso di CI del 16/09 ha trovato cio' che
   tre passate di review locali non avevano visto.

---

## Quel che resta

**L9 — Giornata del cliente e parita' `/m`**: account nuovo percorso in ordine cliente,
stati vuoti, CTA morte, coppie desktop/mobile. Modello: **Fable normale**. Non ha
ancora un prompt scritto.

Cio' che e' **fuori perimetro per scelta** (rendering `.tsx`, 7 funzioni SQL di staff,
copertura oltre il 61%, 96 policy RLS) e' elencato con la sua ragione in
`AUDIT_COPERTURA.md` — perche' nessun audit futuro lo riscopra come una novita'.
