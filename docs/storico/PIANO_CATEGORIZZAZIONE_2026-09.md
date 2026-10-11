> **ARCHIVIATO l'11/10/2026 — piano chiuso il 04/09/2026 (10 fasi su 10).** Era in
> `docs/piani/` (git-ignorato); i percorsi `scratchpad/...` citati sotto non esistono più.
> Resta come fotografia: il «perché» del motore unico di categorizzazione, della provenienza
> tracciata e del gate di affidabilità. Il «come funziona oggi» sta in
> `DOCUMENTAZIONE/tecnica/AI_PIPELINE.md`.

# Piano — Ristrutturazione del processo di categorizzazione
Sessione di apertura: 2026-09-01. Rendere il processo di categorizzazione governabile:
un solo motore di decisione, provenienza tracciata, un solo gate di affidabilita'.

Piano esteso (diagnosi D1-D18, misure, tabella modello/effort):
`~/.claude/plans/fai-una-analisi-al-humble-bunny.md`

> NB: questo file e' in `.gitignore` (`docs/piani/*.md`) e vive solo in locale.
> E' gia' stato cancellato una volta il 1/9 da un `git clean` di un'altra sessione.

## Decisioni concordate (non ridiscutere senza motivo)
- **Filosofia**: meglio meno righe categorizzate ma corrette, che tutte categorizzate con
  errori dentro. E' gia' la regola dichiarata del progetto, ma oggi vale solo sull'output
  dell'AI (3,6% delle righe): memoria e dizionario (96%) scrivono senza gate.
- **Ordine di esecuzione** (deciso da Mattia, delegato a me): 0 -> 7 -> 1 -> 2 -> 3 -> 4/4bis
  -> 5 -> 6 -> 8.
- **Fase 4 (esclusione dai margini)**: si applica a **tutto lo storico**, senza avvisare il
  cliente. Ma dietro flag disattivato: il delta per sede si misura e si porta a Mattia
  PRIMA di attivarlo.
- **Storico senza provenienza** (S3): 39.143 righe legacy = `legacy`, trattate come `certa`.
  Nessun backfill retroattivo: sarebbe un'invenzione, non un dato.
- **Card in Home (4bis)**: la voce "Righe classificate" viene **promossa**, non duplicata.
  Solo P.V., mai in catena. L'indice di salute NON cambia (resta 4 voci da 25%):
  NON riusare `voci_spente`, esclude anche dal calcolo (fastapi_worker.py:6967).
- **Fuori scope**: cambio modello AI e riscrittura del dizionario.

## Fasi
- [x] Fase 0 — le tre falle che ingannano in silenzio (D11/D17/D18) · `8287bc6` + `79d16b5`
- [x] Fase 7 — recupero righe riconoscibili + brand acqua != acqua · `a252c57`
- [x] Fase 1 — un solo motore di decisione (D14/D15/D12) · `69e1afd`
- [x] Fase 2 — tracciabilita': colonne fonte + fiducia (D1) · `5d8d543` + review `e18fa37` — 2 migration APPLICATE a prod
- [x] Fase 3 — un solo gate per tutte le fonti (D2) · `c7ac47d` — nessuna migration
- [x] Fase 4 — esclusione dai margini dietro flag SPENTO (D3/S1/S2) · 3/9 sera —
      **le RPC vive erano 7, non 19** (misurate su pg_proc: la cifra 19 veniva
      dai file migration, molte funzioni non esistono più a DB). Vedi «Esito
      Fase 4» in coda. ✅ migration `20260903210000` **applicata al DB** —
      verificato su `pg_proc` il 04/09: 7 RPC su 7 hanno `p_escludi_da_verificare`
      (il piano la dava per pendente: era una cifra ereditata, non misurata).
      Resta spento il solo flag Python
- [x] Fase 4bis — card "Righe da classificare" in Home · 3/9 sera — card grande
      sotto la griglia Salute+KPI, sempre visibile, 4 stati (errore ≠ verde);
      voce promossa fuori dall'elenco Salute SOLO sul desktop (il mobile non ha
      la card e tiene la voce; l'indice non si muove: è calcolato dal backend).
      Vedi «Esito Fase 4bis» in coda. ⚠️ NON guardata nel browser (vincolo
      dichiarato): va vista alla prima occasione su un PV giallo e uno verde
- [x] Fase 5 — apprendimento chiuso sui 3 percorsi (D5) · 3/9 sera — funzione
      canonica `salva_correzione_in_memoria_locale` su batch + PATCH riga +
      riparto/riga-categoria; `memoria_aggiornata` nella risposta (niente più
      `ok: True` col salvataggio fallito). **Trovato e chiuso in corsa**: il
      batch scriveva `classificato_da: "User"`, invisibile ai check
      `startswith('Manuale')` — **319 correzioni reali sovrascrivibili
      dall'auto-save**; protezione estesa alla grafia legacy (`_e_override_manuale`,
      fonte unica sui 3 punti). 16 test, 3 mutanti / 3 uccisi
- [x] Fase 6 (codice) — bonifica memoria globale (D4) · 3/9 sera — il bypass ora
      richiede una CONFERMA: (alta/altissima **e** `verified`) o streak>=3. Le
      **378 voci alta non verificate** (357 solo-AI, cifra ri-confermata a DB)
      passano a hint; la promozione via streak resta. 6 test, 2 mutanti / 2
      uccisi; suite AI 275 verde. ⚠️ **Parte DATI a Mattia**: i conflitti
      utente↔master sono **153 oggi (116 con correzione manuale, erano 83
      l'1/9)** — risoluzione a favore del cliente via categorization-reviewer,
      con la sua approvazione
- [x] Fase 6-bis (codice) — la via di rientro non esisteva · 4/9 — «la promozione
      via streak resta» (riga sopra) era **falso**: in
      `aggiorna_streak_classificazione` la guardia usciva su
      `confidence in ('alta','altissima')`, cioe' esattamente la condizione
      delle voci declassate dalla Fase 6. Lo streak non saliva mai, la soglia
      non si raggiungeva e le 373 voci restavano a chiamare l'AI **per sempre**.
      Prova a DB (4/9): le `alta` non verificate sono **378**, di cui **373
      bloccate a streak 0** (le altre 5 erano gia' rientrate); le 373 hanno
      streak **tutte 0**
      (0 a 1, 0 a 2), mentre il gruppo di controllo `media` — dove la guardia
      non interveniva — distribuisce 720/128/16 su streak 0/1/2. Guardia
      corretta su **entrambi** i rami (match esatto e gemello normalizzato):
      si esce solo per chi e' gia' in bypass (verified, o streak a soglia).
      Soglia e livelli estratti in `CONFERME_PER_BYPASS` / `CONFIDENCE_ALTA`
      (`config/constants.py`), erano ripetuti a mano in 9 punti. 3 test nuovi,
      3 mutanti / 3 uccisi (guardia originale, fix parziale sul solo ramo
      gemello, guardia rimossa). Impatto: 230 delle 373 voci compaiono in
      fatture reali — 469 righe / 28.107 € negli ultimi 90 giorni (cifre
      ri-misurate due volte con query indipendenti; ultima fattura toccata: 4/9,
      il flusso era attivo). Review `code-reviewer`: 🟢 chiusa correttamente.
      **Effetto dichiarato**: la categoria di una voce declassata non e' piu'
      immutabile — l'AI puo' correggerla (NOCE DI MANZO→FRUTTA si auto-corregge)
      e lo streak riparte da 1; un `verified` resta intoccabile. 4 test, 4
      mutanti / 4 uccisi. **Da tenere d'occhio** (non bloccanti): (a) sul
      percorso upload l'hint passato all'AI E' la categoria della voce stessa,
      quindi la 3ª conferma non e' sempre un giudizio indipendente — se il tasso
      d'errore sulle auto-promosse restasse alto, la leva e' togliere l'hint alle
      declassate, non alzare la soglia; (b) `hint=None` sul percorso SDI
      (`queue_processor.py:371`), da capire se deliberato — **misurato il 4/9**:
      su **238 righe tracciate** (il campo `categoria_fonte` esiste dal 9/8:
      luglio e' 0% tracciato, agosto 42,5%, settembre 100% — NON e' una misura
      su 30 giorni pieni) le fonti dominanti sono `L2_locale` (127 righe),
      `L1_5_non_negoziabile` (71) e `L7_dizionario` (11), tutti livelli che
      decidono PRIMA di arrivare al modello; `AI_alta` compare 4 volte. L'anello
      "l'hint conferma se' stesso" e' reale ma oggi passa pochissimo traffico:
      intervenire li' sposterebbe poco. Da rivedere solo se la misura dell'11/09
      mostra un tasso d'errore alto sulle auto-promosse
- [ ] **Misura dell'11/09** (`PROMPT_COSTO_AI_DOPO_FASE6.md`) — ora leggibile con
      `python -m scripts.audit_fase6_rientro_bypass`: stampa la distribuzione
      dello streak per declassate vs gruppo di controllo e da' un verdetto
      ROSSO/VERDE/INCONCLUSIVO. Distingue "via chiusa" da "nessun traffico", che
      a occhio nudo hanno lo stesso aspetto (5 test, 1 mutante ucciso)
- [x] Fase 8 — igiene tecnica (D8/D10 + D7 ridimensionato) · 3/9 sera —
      **D8**: collasso doppie solo per forme >=6 char (65 keyword corte tipo
      POLLO→POLO, BOLLO→BOLO generavano parole reali; 490→426 pattern; il
      refuso su parola lunga si recupera ancora). **D10**: ground truth A/B con
      anche la grafia `User` (il campione era parziale). `ONEFLUX_AI_MODEL`
      documentata in `.env.example`. **D7 RIDIMENSIONATO DALLA MISURA**: le
      chiamate da 1 articolo sono strutturali all'arrivo SDI una-fattura-per-
      volta; ri-misurato ago-set = 105 chiamate/mese ≈ **0,4-0,5 €/mese** — un
      accumulo cross-fattura nel hot-path d'ingestione non ripaga il rischio.
      La «riduzione su troncamento» ESISTE già (retry a chunk ≤20 sulle righe
      non restituite). 5 test, 2 mutanti / 2 uccisi
- [ ] **NUOVO 1** — il guardrail IVA scarta la risposta giusta (vedi Esito Fase 1) · Opus · Medio
- [x] **NUOVO 2** — D13: la GUC `app.category_change_source` non e' mai settata, serve
  una RPC; il log di audit ha 4.122 righe senza attore (vedi Esito Fase 2) · **chiuso
  l'08/09/2026 come Punto 2 dell'audit** (`2e21b3a`, `6a73b73`, `e3f59ff`, spediti): RPC
  `aggiorna_categoria_fatture_attribuita` + chokepoint `aggiorna_categoria_fatture`, e il
  Punto 3 (`c60ed08`…`fff50ea`) ha aggiunto la guardia sulle righe arbitrate. Review del
  cumulativo 🔴 su due residui (test mancante su `fetch_all`, snapshot a mano): stanno
  nella Parte A di `docs/storico/audit-2026-09/PROMPT_FUNZIONI_SQL_VIVE.md`

## Esito Fase 1 (1/9) — due scoperte che cambiano il piano
1. **I siti erano nove, non sei**, con tre semantiche (ordine A, ordine B, valutazione in
   OR) piu' `fastapi_worker.py:370` che SCRIVE a DB con le sole regole forti.
   Unificati in `decisione_deterministica()`.
2. **D16 e' ROVESCIATO dalla misura.** Il piano voleva estendere il guardrail IVA a tutti
   i livelli. Simulato sulle 1.388 righe candidate reali: 334 cambierebbero, e le
   correzioni vere sono solo le mozzarelle (110 EUR). Il resto sono danni —
   TERRICCIO UNIVERSALE -> PESCE ("RICCI"), ONERI PEREQUAZIONE -> FRUTTA ("PERE"),
   la bolletta dell'acquedotto UI3 ACQUA POTABILE -> ACQUA minerale, BAR CAFFE'
   PASTICCERIE (voce TARI) -> CAFFE E THE.
   **Causa vera**: il guardrail scarta la risposta CORRETTA delle regole forti perche' e'
   ancora una "categoria di spesa generale", e ripiega sul dizionario che sbaglia.
   Va corretto prima, non esteso -> nuova voce in coda.
3. D12 (percorso PDF) chiuso, ma impatto attuale **nullo**: zero righe da PDF a DB
   (39.143 su 39.143 sono XML/P7M). Difetto latente, non attivo.

## Stato / note aperte
- **Misura cieca** (815 righe, baseline in `scratchpad/risultati_giudizio.json`): 96,7%
  corrette. Il margine vero non e' negli errori ma nei "Da Classificare".
- **Righe storiche da ricategorizzare** (serve una decisione di Mattia, NON fatto):
  38 bibite fuori da ACQUA + 12 in coda (Fase 7) + 5 mozzarelle in MATERIALE (Fase 1).
- **Vincolo d'ordine**: Fase 3 prima della 4, o l'esclusione colpisce una fetta arbitraria.
- **D9 da riconciliare prima della migration di Fase 2**: nel DB vivo il constraint e'
  `fatture_categoria_not_empty_chk`; la migration
  `20260429223000_enforce_no_unclassified_categoria.sql` non risulta applicata.
- Non pushato: i commit di questa sessione stanno su `main` locale insieme a quelli di
  altre sessioni. Il push spedisce tutto.

## Esito Fase 2 (1/9)
- Colonne `categoria_fonte` / `categoria_fiducia` su `fatture`, **migration applicata al
  DB di produzione** (autorizzata da Mattia). 39.233 righe tutte a NULL = legacy = certa.
- Popolate da tutti i percorsi: 11 livelli di `categorizza_con_memoria`, gate upload,
  gate worker, e i **quattro** endpoint di correzione manuale (`correzione_cliente`/`certa`).
- **D13 NON chiuso, e va detto**: il piano voleva loggare anche gli INSERT nel
  `category_change_log`. Scartato — ~39.000 righe che dicono solo "la riga e' nata",
  gia' in `created_at` e ora in `categoria_fonte`. Il difetto vero resta aperto: 4.122
  righe di log, tutte `source='db_trigger'` e `actor_email` NULL, perche' la GUC
  `app.category_change_source` non e' settata da nessun percorso Python. Serve una RPC
  (PostgREST non espone SET LOCAL) -> lavoro a se', in coda.

## Esito code review Fasi 1+2 (1/9) — verdetto iniziale 🔴, ora chiuso
Tre blocchi, tutti fondati e verificati in prima persona prima di correggere:
- **B2**: la fonte era decisa PRIMA che la categoria fosse definitiva. 68 combinazioni
  reali con riga in coda ma fonte "L4_dicitura"/"L1_5_non_negoziabile". Dopo il fix: 0.
  Il commento che avevo scritto in `invoice_service.py` era falso e l'ho corretto.
- **B1**: i percorsi scoperti erano SEI, non zero come dichiarava il commit di Fase 2.
  Il peggiore: l'agent notturno buttava via una fonte che aveva in mano.
- **B3**: `correzione_cliente` non era in `_FONTI_CERTE` -> `da_verificare`.
Non bloccanti chiusi: `findall`->`finditer` (ramo morto), comment della colonna
disallineato (migration `20260901183000`, applicata).

**Aperto e documentato nel codice**: il percorso PDF/Vision non registra la provenienza.
Impatto oggi nullo (0 righe da PDF), ma la Fase 1 lo ha reso capace di classificare:
va chiuso PRIMA che un cliente carichi PDF.

**Da rifare a ogni fase**: la review va lanciata su ogni fase, non a fine sessione.
Questa ha trovato 3 blocchi su lavoro che avevo gia' dichiarato chiuso.

## Modello consigliato per la fase successiva
Fase 4 — **Opus + `ultrathink`**, effort **Alto**. Alto per **estensione, non per
difficolta'**: la logica e' una riga (escludi `da_verificare`), ma va applicata a **19 RPC**
e il rischio vero e' dimenticarne una — un'esclusione parziale falsa il MOL peggio di
nessuna esclusione. E' la prima fase che cambia COSA entra nei margini: da qui in poi le
decisioni toccano i numeri che il cliente vede. Dietro flag disabilitato.

## Esito Fase 3 (1/9) — la misura ha rovesciato il piano, per la terza volta
- `_fiducia_per_fonte` (tabella statica che non guardava mai la riga) diventa
  **`valuta_fiducia(fonte, categoria, descrizione, fornitore)`**: pura, senza mock.
- **Il gate del piano era sbagliato.** Simulato su 33.147 righe reali / 4,1 M EUR:
  "il deterministico deve confermare" boccia l'8,6% delle righe (364.000 EUR) e sbaglia.
  Il SILENZIO del dizionario non e' dubbio (TARIFFA PUN -> UTENZE e' corretto, decide la
  memoria); il DISSENSO non predice l'errore, anzi ha torto il deterministico (KG5 KETCHUP
  -> dice MANUTENZIONE, SALSE E CREME e' giusta). Come per il guardrail IVA e la memoria
  globale: la terza volta che "il deterministico e' il metro" cade sotto misura.
- **Criterio adottato (Mattia, 1/9): conservativo.** Declassa **429 righe / 38.323 EUR**
  (1,10% delle righe, 0,94% dell'importo) — "1 ACCONTO" (14.000 EUR), "COMMISSION",
  "SALDO", "RICARICHE": descrizioni che nessun umano categorizza senza aprire la fattura.
  Fonti CERTE mai declassate.
  > La prima misura diceva 280 righe / 38.193 EUR: era su un campione **troncato** dal
  > `limit 4000` della query (33.147 righe su 39.043). Il conteggio era sottostimato del
  > 35%, l'importo quasi giusto perche' le righe mancanti erano di basso valore. Ri-misurato
  > sulle 6.974 combinazioni complete, con impronta verificata contro il DB. Trovato dalla
  > code review: **una misura va verificata anche quando conferma cio' che si sperava.**
- **Nessun numero cliente cambia, per costruzione**: `margine_service.py` non contiene
  `needs_review`; verificato a DB `da_verificare = 0` su tutte e 10 le sedi.
- Chiusi: la fiducia hardcodata dell'agent notturno, e **il debito PDF/Vision**
  (`ottieni_categoria_prodotto` ora registra la provenienza su 9 uscite + reset iniziale).
- Verifica finale (dopo le due review): **12.447 test verdi**, 44 skip, golden set 8.378
  incluso; `check_documentazione.py` pulito; **quattro mutanti** provati su copia in
  scratchpad — gate spento (429 -> 0, 6 test rossi), declassa le fonti certe (9 rossi),
  `return` nudo in `ottieni_categoria_prodotto` (ucciso dal test strutturale), rimozione
  del reset iniziale (**sopravvissuto**: il reset e' ridondante, ogni uscita gia' scrive.
  Corretto il commento che lo chiamava "la parte che conta" — il difetto era la mia
  descrizione, non il codice).

### Cifre ri-misurate il 1/9 (non ereditate)
39.224 righe attive · **0 con provenienza** (il codice di Fase 2 non e' mai girato: non
pushato) · 181 in coda · 338 dubbie per 26.394,89 EUR · 2.913 voci master (1.242 non
verificate). Il primo dato reale di provenienza arrivera' dopo il push.

### Da sapere per la Fase 4
- L'impatto della Fase 4 va **ri-misurato dopo il push**: oggi `da_verificare` e' 0 a DB,
  quindi la tabella per sede del piano esteso non e' piu' la stima giusta.
- `git log origin/main..main` dice **0 commit in coda**, non 51: il ref `origin/main`
  locale coincide con `main` (ultimo fetch 1/9 20:15). O un'altra sessione ha pushato, o
  il ref e' stale. **Non ho toccato il remote**: da chiarire prima del deploy serale.

### Seconda code review Fase 3 (hook sul path sensibile) — verdetto 🟢
Focus sulle inerenze: chi altro chiama i contratti toccati. Nessun blocco. Verificato
che i due percorsi (XML e PDF) non si inquinano a vicenda sul ContextVar, che il PDF non
passa mai dal worker HTTP, e che `_ret_ocp` cattura la descrizione giusta.
Chiusi due non bloccanti (`16fd118`):
- il PDF senza `user_id` scriveva NULL, che per contratto vuol dire "legacy = certa": ora
  scrive `nessuna`. Il guard su "Da Classificare" non bastava perche' `force_categoria`
  promuove la riga a NOTE E DICITURE subito dopo.
- `_ret_ocp` non passava `fornitore` a differenza di `_ret`: inerte oggi, divergenza
  silenziosa domani.

**Agli atti, senza modifiche**: il ramo `AI_alta` del gate e' difensivo e non attivo —
entrambi i percorsi AI assegnano quella fonte solo dopo aver gia' verificato
`not descrizione_e_dubbia(...)`. Il gate serve a memoria e dizionario, il 96%.

**Due cose che nessuna delle due review ha potuto verificare**, e non vanno date per buone:
la **CI** (i commit non sono su `origin/main`, `tests.yml` non e' mai girato su di essi;
gira su Python 3.12 e include `legacy_streamlit`, io ho misurato su 3.11) e il **DB live**
dalla sessione del reviewer (permesso negato al suo MCP). Le 429 righe / 38.323 EUR e
`da_verificare = 0` li ho misurati io in questa sessione.

### Chiusura sessione 1/9
Fase 3 chiusa in 3 commit: `c7ac47d` (fase), `4687e11` (3 blocchi prima review),
`16fd118` (2 non bloccanti seconda review). **In coda 7 commit, 4 miei** — gli altri 3
(`6aa58e7`, `f3490e4`, `ed754c8`, `d9e2003` = sparkline/dashboard) sono di una sessione
parallela: **non miei, non li spedisco io**.

**Due cose che nessuno ha verificato**, da dire prima del push:
1. **La CI non e' mai girata** su questo lavoro: niente e' su `origin/main`. Gira su
   Python 3.12 e include `legacy_streamlit`; io ho misurato in locale su 3.11.
2. **Il conteggio dei commit in coda non torna**: `origin/main..main` dice 0, ma
   `e18fa37..main` dice 7. Il ref locale e' disallineato. Non ho toccato il remote.

Prossima sessione: **non aprire la Fase 4** senza che Mattia abbia sciolto il punto 2.

### DEPLOY ESEGUITO — 1/9/2026 22:43 UTC
`git push origin main`: **e18fa37..0234da8**, 8 commit (3 miei di Fase 3 + 5 della
sessione dashboard/sparkline). Coda residua: 0.

- **CI verde alla prima**, incluso il dubbio aperto: gira su Python 3.12 + Deno, io avevo
  misurato in locale su 3.11. Tests ok, OpenAPI Drift ok, Requirements ok, Vercel ok.
- **Railway ridispiegato**: `/health` risponde 200 e riporta `commit 0234da819675` — il
  codice in produzione e' quello pushato.
- **A DB subito dopo il deploy: 0 righe con provenienza** su 39.224 attive. Atteso: il
  gate scrive solo sulle righe NUOVE, e non e' ancora arrivata una fattura. Lo storico
  resta `certa` (nessun backfill): il MOL dei mesi chiusi non si e' mosso.

**Il primo dato reale di provenienza arriva con la prossima fattura.** E' li' che va
ri-misurato l'impatto della Fase 4, non prima.

### Due cifre che avevo dato sbagliate (corrette qui per non propagarle)
- «51 commit in coda» era **ereditato dal prompt, non misurato**: erano 7, poi 8. Il ref
  `origin/main` era stale; il `git fetch` l'ha sciolto. Terza volta in questo progetto che
  una cifra ripresa da un documento si rivela falsa.
- «4 commit miei» erano **3** (`c7ac47d`, `4687e11`, `16fd118`).

---

## 2/9/2026 — Chiusura documentale + un bug trovato per strada

**Il gate funziona in produzione.** Prima misura reale: 25 righe nuove dopo il deploy,
**25 con provenienza, zero senza**. Tutte `certa` (`L2_locale` 19, `L1_5_non_negoziabile`
6): corretto, sono fonti che il gate non declassa per regola. `da_verificare` = 0 perche'
nessuna riga con descrizione dubbia e' ancora arrivata.

### Il bug in Home (trovato controllando le altre sedi, su richiesta di Mattia)
`fastapi_worker.py` sceglieva il testo della voce "Righe classificate" su `tot_righe`
(righe caricate negli ultimi 30 giorni) invece che su `da_controllare`. **4 sedi su 11**
leggevano "Nessuna riga da classificare" pur avendone — la peggiore 187 righe, ferma dal
21 luglio. Pallino e deep-link erano corretti: mentiva solo la frase.
Estratta `_dettaglio_righe_classificate()` pura, **10 test**, 2 mutanti uccisi.

### Debito §5bis saldato
- eliminato `docs/piani/PROMPT_PROSSIMA_SESSIONE.md` (diceva "51 commit in coda" ed e'
  la fonte da cui questa sessione ha ereditato quella cifra falsa);
- `check_piani_orfani()` ora guarda **tutti** i `.md` di `docs/piani/`, non solo
  `PIANO_*` — provato per mutazione;
- `AI_PIPELINE.md` v7.0: fonti canoniche al posto dei "5 livelli", sezione sul gate,
  e **rimosso il fallback a "SERVIZI E CONSULENZE"** che il doc descriveva ancora
  (eliminato dal codice da giugno, vietato da CLAUDE.md);
- `DATABASE_SCHEMA.md`: le due colonne di provenienza + il CHECK + "NULL = legacy";
- verbale nello storico; `AUDIT_COPERTURA.md` **ri-misurato** (`ai_service.py` e' 5.715
  righe, non 5.405);
- piano rinominato `PIANO_SESSIONE_CORRENTE.md` -> `PIANO_CATEGORIZZAZIONE.md` (§2).

## Modello consigliato per la fase successiva
Fase 4 — **Opus + `ultrathink`**, effort **Alto**. Alto per estensione, non per
difficolta': la logica e' una riga (escludi `da_verificare`), ma va applicata a **19 RPC**
e il rischio e' dimenticarne una — un'esclusione parziale falsa il MOL peggio di nessuna
esclusione. Dietro flag disattivato, delta per sede misurato e portato a Mattia prima di
attivarlo.

### Trovati dalla code review del 2/9 — PREESISTENTI, non aperti da me
1. **La card conta righe, la campanella prodotti distinti.** Sulla stessa sede e
   nella stessa schermata: 187 vs 112 (SUSHILAND SAN GIULIANO), 156 vs 100, 45 vs 29.
   La divergenza e' consapevole a monte (decisione 28/06 di allineare il briefing alla
   pagina) ma la card non e' mai stata allineata. **Decisione di prodotto per Mattia**,
   non una correzione tecnica.
2. **`righe_mese` in `home_salute` e' troncato a 1000 righe** (`fastapi_worker.py`,
   `.execute()` diretto) mentre il gemello `_salute_indice_rosso` usa `fetch_all()` col
   commento «troncare qui falserebbe la % di righe classificate». Oggi 2 sedi troncano
   (3.344 -> 1.000 e 1.564 -> 1.000): impatto 1 punto percentuale, nessun colore cambia.
   Stessa classe della lezione «misura su campione troncato»: cresce se i `needs_review`
   si spostano oltre le prime 1000 righe.
3. Minore: la query `da_controllare` scarica fino a 1000 righe per leggere un contatore
   (manca `.limit(1)` / `head=True`, che la nuova query invece usa).

### DEPLOY 2/9/2026 09:07 CEST — solo i miei 3 commit
`0234da8..c2b566d`. Isolati su ramo temporaneo da `origin/main` (i 2 commit della
sessione impostazioni/password sono rimasti in locale, su richiesta di Mattia), poi
`main` locale riallineato con `rebase origin/main`: il rebase ha riconosciuto i miei 3
come gia' applicati e li ha scartati, riapplicando solo i 2 altrui. **Nulla perso**:
suite 12.479 verde dopo il rebase, i file della sessione parallela intatti.

- **CI verde alla prima** (Tests su Python 3.12, OpenAPI Drift, Requirements). Nessun
  deploy Vercel: corretto, non ho toccato `apps/web`.
- **Railway ridispiegato**: `/health` riporta `commit c2b566d1fa23`.
- **Verificato l'effetto reale a DB**: le 4 sedi che leggevano "Nessuna riga da
  classificare" ora mostrano 187 / 30 / 10 / 1 righe da controllare; CASATI 14
  (0 righe) resta correttamente "Tutte le righe sono classificate".
- Deploy alle 9 del mattino, **fuori dalla finestra serale**, su istruzione esplicita di
  Mattia. Segnalato prima di procedere.

**In coda restano 2 commit, non miei** (`872c41d` impostazioni, `04fff62` password):
li spedisce la loro sessione.

---

## Esito Fase 4 (3/9 sera) — la misura ha ridimensionato il piano, di nuovo

- **Le RPC col filtro 'Da Classificare' vive a DB sono 7, non 19** (misurate su
  `pg_proc` il 3/9): `costi_automatici_mensili`, `costi_automatici_mensili_gruppo`,
  `gruppo_peso_categoria`, `gruppo_prezzi_categoria` (**senza chiamanti nel
  repo**, inclusa per coerenza), `gruppo_spesa_pivot`, `gruppo_spreco_fb_categorie`,
  `gruppo_tag_descrizioni`. La cifra «19» veniva dal grep sui file migration:
  contava funzioni superate/rinominate. `gruppo_salute_componenti` guarda
  `needs_review` ma è un contatore della coda, non un calcolo margini: esclusa
  di proposito.
- **Meccanica del flag**: costante `ESCLUDI_DA_VERIFICARE_DAI_MARGINI = False`
  (config/constants.py) + `CATEGORIA_FIDUCIA_DA_VERIFICARE` fonte unica.
  Lato query: helper `escludi_da_verificare_margini()` in db_service (NULL-safe:
  `or_(is.null, neq)` — un `.neq` secco butterebbe fuori le 39.224 righe legacy
  NULL=certa), applicato ai **6 punti Python** che filtrano DC per i margini
  (margine_service :90 e :292; fastapi_worker `_load_fatture_fb_for_period`,
  `_load_fatture_fb_per_categoria_e_mese`, `_calcola_costi_auto_per_mese`,
  `_calcola_costi_auto_per_periodo`). Lato RPC: helper `rpc_params_fase4()` sui
  6 chiamanti — **a flag spento il parametro NON viene passato**, la chiamata è
  byte-identica a prima: il codice può andare in produzione prima o dopo la
  migration, in qualsiasi ordine.
- **Migration** `supabase/migrations/20260903210000_fase4_escludi_da_verificare_flag.sql`:
  DROP+CREATE (un parametro nuovo con DEFAULT su una funzione esistente creerebbe
  un overload ambiguo per PostgREST) con `p_escludi_da_verificare boolean DEFAULT
  false` e condizione `COALESCE(f.categoria_fiducia,'') <> 'da_verificare'`;
  REVOKE/GRANT ristabiliti (chiude anche il residuo anon/authenticated su
  `costi_automatici_mensili_gruppo`). ✅ **Applicata al DB** (verificato su
  `pg_proc` il 04/09: 7 su 7). Era data per pendente, non lo era. Aggiornata da
  Mattia (o su suo ordine), come per la Fase 2.
- **Delta per sede misurato il 3/9: ZERO su tutte le 11 sedi** — a DB ci sono 0
  righe `da_verificare` (39.224 NULL legacy, 215 certa, 21 probabile). Attivare
  oggi non cambierebbe nessun numero: il flag comincia a mordere man mano che
  arrivano righe nuove con descrizione dubbia. Il delta va RI-misurato al
  momento del flip, non ereditato da qui.
- **Presidio**: `tests/test_fase4_esclusione_da_verificare.py` — flag spento =
  nessun effetto (query e RPC), clausola NULL-safe, stessa stringa su gate
  Python / filtro / migration, default SQL spento. **5 mutanti / 5 uccisi**
  (helper sempre-attivo, via l'is.null, parametro sempre passato, stringa
  divergente nella migration, costante divergente dal gate). Suite margini,
  gruppo e costi: 578 verdi.

**Ordine di attivazione (per Mattia, quando vorrà):**
1. ~~applicare la migration `20260903210000` al DB~~ — **già applicata** (verificato il 04/09);
2. ri-misurare il delta per sede (query nel presidio/verbale) e guardarlo;
3. `ESCLUDI_DA_VERIFICARE_DAI_MARGINI = True` + deploy;
4. Fase 4bis (la card in Home) DEVE essere già visibile, o i numeri calano
   senza spiegazione.

## Modello consigliato per la fase successiva
Fase 4bis — card «Righe da classificare» in Home · **Sonnet** · Basso (frontend
su pattern esistente; Opus solo se si tocca l'importo lato backend). Poi 5, 6, 8.

## Esito Fase 4bis (3/9 sera)

- **Backend**: `SaluteResponse.da_classificare` (righe + importo), calcolato da
  `_card_da_classificare()` col predicato IDENTICO ai margini (categoria
  'Da Classificare'; + `da_verificare` a flag Fase 4 acceso) — NON `needs_review`,
  che include 338 righe legacy classificate-ma-dubbie che nei margini CI SONO:
  sarebbe di nuovo il difetto card-vs-campanella del 2/9. Su errore il campo è
  `None` e la card mostra l'errore, mai il verde (lezione card-segnali).
- **Frontend**: logica pura in `lib/home-da-classificare.ts` (stati + promozione
  della voce), card in `dashboard/da-classificare-card.tsx`, blocco a larghezza
  piena sotto la griglia in `dashboard/page.tsx` (stesso `fetchSalute` cache():
  zero round-trip in più; BlockRetry sugli stati di errore). La voce
  "classificate" esce dall'elenco della card Salute SOLO sul desktop: il mobile
  non ha la card grande e la tiene, la catena non è toccata (ha la sua gemella).
- **Provata sui 4 stati** con l'harness node (il rendering resta fuori, come
  tutta la UI): errore su salute nulla/dato assente, verde solo a zero vero,
  contatore+€+deep-link, singolare/plurale. **4 mutanti / 4 uccisi** (falso
  verde sul dato assente, promozione che non filtra, backend che torna 0 su
  errore, backend che conta needs_review). Suite salute/home: 188 verdi; a
  campione sui dati veri: San Giuliano 46 righe / 944,89 €, TIME CAFE e CASATI
  verdi, LAND **−1.302,36 €** (note di credito non classificate: la copy regge
  anche il negativo). Indice: formula non toccata (188 test verdi), la voce
  resta nel calcolo.
- **Non fatto e dichiarato**: la card non è stata guardata nel browser (qui non
  c'è); `tsc --noEmit` pulito ma non prova nulla. Da guardare alla prima
  occasione. La sede tecnica «Costi comuni di gruppo» ha una Home PV
  raggiungibile e mostrerebbe 48 righe / 1.270,24 €: onesto, ma da sapere.
- **SUPERATO il 9/9/2026** da un lavoro separato (piano «briefing: togliere la
  ripetizione, fondere il banner»). Guardata finalmente nel browser, la card
  grande risultava un doppione di quella che il briefing mostra già in cima
  («2 prodotti da controllare»): due blocchi con due numeri diversi che al
  cliente sembrano la stessa cosa. Decisione di Mattia: **una card sola, due
  righe**, e a zero righe non si mostra nulla — il verde «tutte classificate»
  sparisce. `lib/home-da-classificare.ts`, `dashboard/da-classificare-card.tsx`
  e `tests/test_home_da_classificare_frontend.py` sono stati **eliminati**; la
  voce «Righe classificate» è tornata nell'elenco della card Salute desktop.
  Resta `_card_da_classificare()`, che ora serve il briefing: gli euro esclusi
  viaggiano nel payload di `uncategorized_rows` come seconda riga della card.
  Le due popolazioni (prodotti `needs_review` vs righe 'Da Classificare')
  restano **due frasi separate**: legarle in una sola sarebbe falso.

## Modello consigliato per la fase successiva
Fase 5 — chiudere l'apprendimento sui 3 percorsi (D5) · **Sonnet** · Basso.

---

## Esito fasi 5, 6, 8 (03-04/09) — chiuse fuori da questo ciclo

Le ultime tre fasi **sono state eseguite dalla sessione Fable**, un lavoro
autonomo e separato da questo ciclo, il cui racconto vive in
`docs/storico/audit-2026-09/AUDIT_CON_FABLE.md` (§3 «Categorizzazione — le 5 fasi rimaste»).
Non le ha eseguite questo piano: qui si registra solo il fatto tecnico. Qui si
registra **solo il fatto tecnico**, perché questo piano non menta per omissione:
si fermava alla 4bis mentre il codice era già avanti.

Misurato sui commit (04/09), non ripreso dai documenti:

- **Fase 5** — `cab7db1`: l'apprendimento dalle correzioni manuali unificato sui
  3 percorsi (`ai_service.py`, `routers/fatture.py`, `routers/riparto.py`), con
  `tests/test_fase5_apprendimento_unificato.py` (230 righe).
- **Fase 6** — `c17e2db`: il bypass della memoria globale richiede una conferma
  umana, con `tests/test_fase6_memoria_bypass_verificato.py`.
- **Fase 8** — `8dd7a2e`: il correttore di refusi non scambia più le parole corte
  (`POLLO`→`POLO` mandava una polo da 60 € in CARNE), con
  `tests/test_fase8_igiene.py`.

**Il piano è quindi completo: 10 fasi su 10.**

### Cosa resta a carico di Mattia (non è lavoro di codice)

- ~~**Migration `20260903210000` NON applicata al DB**~~ — ✅ **è applicata**:
  verificato su `pg_proc` il 04/09, 7 RPC su 7 espongono `p_escludi_da_verificare`.
  Il documento la dava per pendente da tre punti diversi: nessuno l'aveva misurata.
- **Flag `ESCLUDI_DA_VERIFICARE_DAI_MARGINI` = `False`** (`config/constants.py`):
  si accende solo dopo la migration e dopo aver ri-misurato il delta per sede.
  Delta misurato il 03/09: zero su 11 sedi. ⚠️ **Ri-misurato il 04/09 sera: NON è più zero** —
  **340 righe** classificate-ma-dubbie su **10 sedi**, per **26.453 €** che uscirebbero dai
  margini (SUSHILAND VILLA GUARDIA 13.704 €, SAN GIULIANO 12.612 €, il resto sotto i 200 €).
  La misura va **rifatta al momento di accendere il flag**, non ereditata da qui.

### Nota di misura

Il piano dava la Fase 4 come «19 RPC da toccare»: le RPC vive erano **7**,
misurate su `pg_proc` invece che contate sui file migration. È la settima volta
in questo ciclo che una cifra ereditata da un documento non regge alla misura.

---

## Modello consigliato — dopo la chiusura del piano (04/09)

**Il piano è chiuso: 10 fasi su 10. Non c'è una «fase successiva» qui dentro.**
La riga «Fase 5 · Sonnet» più sopra è la raccomandazione dell'1/9, ormai
superata: si legge come storia, non come indicazione.

Il lavoro riparte dalla roadmap del ciclo (`AUDIT_ONEFLUX_STATO_2026-09.md` §0
«I prossimi passi»), non da questo file. Per quel che tocca la categorizzazione,
resta **fuori dal codice**: la migration da applicare e il flag da accendere,
entrambi a carico di Mattia, con il delta ri-misurato al momento — non ereditato
da qui.

Se una di quelle due azioni apre lavoro di codice, il default di `WORKFLOW.md` §3
vale come sempre: **Opus**, con `ultrathink` in apertura perché si tocca
l'esclusione di righe dai margini, cioè una regola di dominio.
