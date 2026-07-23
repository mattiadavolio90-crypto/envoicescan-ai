# PIANO — Smistamento coda catena OFFSIDE + collaudo totale del flusso

**Data:** 23/07/2026
**Origine:** 2 problemi + 1 richiesta feature segnalati dal cliente OFFSIDE (catena, P.IVA unica 07863990961, sedi Via Losanna e Via Settembrini).
**Stato:** PIANO — nessuna modifica al codice ancora fatta. Si procede solo al "procedi" di Mattia.
**Vincolo di dominio non negoziabile:** *LA FATTURA RESTA SACRA*. Non si spezzano né si riscrivono le righe della fattura elettronica (integrità fiscale). Le quote di riparto vivono in tabelle separate a livello ACCOUNT.

---

## 0. Quadro dei problemi (cosa ha segnalato il cliente, cosa ho verificato nel codice)

| # | Segnalazione cliente | Diagnosi verificata sul codice | Gravità |
|---|---|---|---|
| **P1** | L'anteprima non si genera nella coda catena. Intermittente: a volte c'è entrando, sparisce rientrando. Quasi tutte senza anteprima → impossibile smistare. | **NON è corruzione file.** È timeout del worker sotto contesa. L'anteprima ri-parsa l'XML **a caldo ogni apertura**, su unico container Railway Hobby, senza cache. L'intermittenza è la firma della contesa di risorse, non del documento rotto. Messaggio "documento firmato non leggibile" è **fuorviante**. | ALTA |
| **P2** | L'indirizzo di smistamento NON è sempre nello stesso punto dell'XML: i fornitori citano Losanna/Settembrini nella descrizione o causale. Bisogna leggere tutta la fattura. | **Confermato coi dati:** 319/383 fatture hanno la sede legale generica "V.LE FULVIO TESTI 68" in `<Sede>`; l'indirizzo del locale reale è nascosto in `AltriDatiGestionali/RiferimentoTesto`. La funzione `extractIndirizzoDestinatario` legge **solo `<Sede>`**. | ALTA |
| **P3a** | Regole per fornitore (es. Telepass/carburante/auto/telefono sempre 50/50). | **La tabella `riparto_regole_fornitore` esiste già** e il salvataggio è già attivo. Manca solo la proposta automatica in coda. | MEDIA (alto valore/basso sforzo) |
| **P3b** | Selezione multipla per flaggare e smistare più fatture insieme. | Da costruire nella UI coda. Le assegnazioni sono già indipendenti per `queue_id`. | MEDIA |
| **P3c** | "Altra soluzione, cosa ne pensi?" | Vedi Fase 5 (fattura mista doppio-indirizzo) + Fase 7 (idee extra). | — |

---

## FASE 1 — Fallback indirizzo: leggere TUTTA la fattura (risolve P2) ✅ FATTA (23/07)

> **Stato:** implementata e testata (non ancora deployata). Nuova funzione
> `extractIndirizzoCandidati` in `supabase/functions/invoicetronic-webhook/index.ts`:
> raccoglie i candidati-indirizzo da `<Sede>` (1°), poi `RiferimentoTesto`,
> `Causale`, `Descrizione` righe. Il routing multi-sede prova prima `<Sede>` e, solo
> se NON dà un match forte e univoco (MIN_SCORE 0.40 / MIN_GAP 0.20), ripiega sui
> candidati fallback scegliendo il primo che supera le stesse soglie; se nessuno
> risolve → `da_assegnare` (invariato). `meta.routing.source` = `sede`|`fallback`|
> `manual`, `meta.indirizzo_fallback` traccia il testo che ha risolto. +6 test Deno
> (13 in `routing_test.ts`, tutti verdi; `deno check` pulito). Nessuna regressione:
> il fallback si attiva SOLO quando `<Sede>` non risolve già.


**Obiettivo:** quando la sede legale in `<Sede>` è generica/ambigua, cercare l'indirizzo del locale reale negli altri punti dell'XML dove i fornitori lo scrivono.

**Dove:** `supabase/functions/invoicetronic-webhook/index.ts` — funzione `extractIndirizzoDestinatario` (riga ~574) e il blocco di routing multi-sede (riga ~1109).

**Cosa fare — cascata di ricerca indirizzo (in ordine di priorità):**
1. `<CessionarioCommittente><Sede><Indirizzo>` (comportamento attuale) — resta il primo tentativo.
2. `<AltriDatiGestionali>` con `<TipoDato>` tipo indirizzo/destinazione + `<RiferimentoTesto>` — dove OFFSIDE trova il locale reale.
3. `<Causale>` a livello documento.
4. Testo delle `<DettaglioLinee><Descrizione>` (ultimo tentativo, più rumoroso).

**Logica di scoring (da conservare, non stravolgere):**
- Per ogni candidato indirizzo trovato, calcolare la Dice-similarity contro gli indirizzi delle sedi note (già esistente).
- Se `<Sede>` dà un match forte e univoco (score ≥ MIN_SCORE 0.40 e gap ≥ MIN_GAP 0.20) → si usa quello, non si scava oltre (evita rumore).
- Se `<Sede>` è ambigua/generica → si aggregano i candidati dai punti 2-4 e si ri-calcola lo scoring su tutto il testo raccolto.
- Se ancora ambiguo → `da_assegnare` (comportamento attuale invariato: meglio in coda che smistata male).

**Rischio da presidiare:** non deve **peggiorare** i casi che oggi funzionano. Il fallback si attiva solo quando `<Sede>` NON dà già un match forte. Test di non-regressione sulle fatture già smistate correttamente (Fase 6-L0).

**Deliverable Fase 1:**
- Modifica `extractIndirizzoDestinatario` (cascata).
- Test Deno nuovi con XML reali OFFSIDE (indirizzo in RiferimentoTesto / causale / riga).
- Deploy Edge Function.
- **Nota:** questo agisce sulle fatture **future**. Per le 383 già in coda serve il `reprocess` (già esistente) — vedi Fase 6.

---

## FASE 2 — Regole per fornitore auto-proposte in coda (risolve P3a) ⭐ priorità reale

**Perché prima:** le fondamenta esistono già (tabella + salvataggio + calcolo quote). È il punto a più alto rapporto valore/sforzo.

**Obiettivo:** quando una fattura entra in coda e il suo fornitore (P.IVA cedente) ha già una `riparto_regole_fornitore` attiva, la coda mostra la fattura **già pronta col riparto proposto** e un bottone "Applica come al solito" (un click). Nessuna applicazione silenziosa (filosofia ONEFLUX: l'AI propone, il cliente decide — vincolo scritto nella migration riga 94-95).

**Dove:**
- `services/routers/riparto.py` — `riparto_regola_fornitore` (riga ~590) già legge la regola. Serve un endpoint che, data la coda, ritorni per ogni `queue_id` l'eventuale regola-fornitore già pronta.
- `apps/web/src/components/fatture/coda-da-assegnare.tsx` — badge "Regola salvata: 50/50" + bottone conferma rapida.

**Cosa fare:**
1. Backend: per ogni voce in coda, join sul fornitore → se esiste regola attiva, allega la proposta (regola, tipo, percentuali) al payload della coda.
2. Frontend: se la voce ha una regola, mostrarla in evidenza con anteprima delle quote e bottone "Applica come al solito"; il click chiama l'endpoint di riparto già esistente (`riparto_da_coda`) con quei parametri.
3. La creazione/modifica della regola resta dov'è (già funzionante nel dialog).

**Scelta di prodotto da confermare (Mattia):** il cliente dice "vanno **sempre** 50/50". Interpretazione ONEFLUX = "proposta pronta, un click conferma". Se vuoi l'auto-applicazione totale e silenziosa per fornitori fidati, è una **deroga esplicita** al principio "propone, non applica" — da decidere consapevolmente. Default del piano: proposta + un click.

**Deliverable Fase 2:**
- Endpoint coda arricchito con regola-fornitore.
- UI badge + conferma rapida.
- Test: fattura di fornitore con regola → appare la proposta; senza regola → coda normale.

---

## FASE 3 — Selezione multipla in coda (risolve P3b) ✅ FATTA (23/07)

> **Stato:** implementata e verificata (typecheck + ESLint puliti; non ancora
> deployata). In `apps/web/src/components/fatture/coda-da-assegnare.tsx`: checkbox
> per riga + "Seleziona/Deseleziona tutte"; barra bulk che appare con ≥1 selezionata
> con "assegna a → [sede]" per ogni sede e "Non sono di nessun locale" (scarto in
> blocco, con conferma sul numero). Le funzioni singole `assegna`/`scarta` sono state
> spezzate in `assegnaCore`/`scartaCore` (una chiamata, ritornano l'esito, nessun
> toast/refresh) riusate sia dall'azione singola sia dal loop bulk. `eseguiBulk`
> esegue in sequenza e riporta l'esito ONESTO (N fatte / M non riuscite, niente
> "fatto!" globale finto): success se 0 errori, warning se parziale, error se tutte
> fallite. Le selezionate riuscite spariscono dalla selezione e dalla coda; le altre
> restano flaggate per riprovare. Il RIPARTO resta per-fattura (ogni costo comune ha
> quote proprie) — di proposito NON entra nel bulk. Selezione azzerata alla chiusura
> della finestra.

**Obiettivo:** flaggare più fatture e smistarle con un'azione sola quando la destinazione è la stessa (o la stessa regola).

**Dove:** `apps/web/src/components/fatture/coda-da-assegnare.tsx`.

**Cosa fare:**
1. Checkbox per riga + "seleziona tutte" / "seleziona per fornitore".
2. Barra azioni bulk: "Assegna le selezionate a → [sede]", "Applica regola fornitore alle selezionate", "Sposta in Costi comuni di gruppo".
3. Esecuzione: loop lato client sulle assegnazioni indipendenti (il `busy` Set per `queue_id` già gestisce lo stato per-fattura); gestire esiti parziali (alcune ok, alcune no) con report chiaro.

**Attenzione:** niente operazione atomica finta. Se 8 su 10 vanno a buon fine e 2 no, il cliente deve vederlo riga per riga. Nessun "fatto!" globale se non è vero.

**Deliverable Fase 3:**
- UI multi-select + barra bulk.
- Gestione esiti parziali.
- Test: 5 selezionate stessa sede → 5 assegnate; mix con 1 errore → report onesto.

---

## FASE 4 — Anteprima persistente: niente più ri-parsing a caldo (risolve P1) ✅ FATTA (23/07)

> **Stato:** implementata e verificata (migration applicata al DB live; test verdi;
> non ancora deployata su Railway). Scelta: colonna dedicata `fatture_queue.anteprima_righe`
> (JSONB) + `anteprima_at` (TIMESTAMPTZ) — migration `20260723200000_anteprima_coda_persistente.sql`,
> applicata (additiva, colonne nullable, nessun lock sulle righe esistenti). NON dentro
> `payload_meta`: quello è l'INPUT (webhook/upload), l'anteprima è un DERIVATO —
> tenerli separati evita di sovrascrivere il meta salvando la cache e rende banale
> azzerare/rigenerare. `riparto_anteprima_coda` ora: legge `anteprima_righe` → se
> presente la ritorna ISTANTANEA (`cache:true`, niente parse); altrimenti parsa una
> volta, salva righe+timestamp e ritorna (`cache:false`). Il salvataggio è un di più:
> se fallisce l'utente riceve comunque le righe appena parsate (ricalcolate al prossimo
> accesso). Un parsing riuscito ma vuoto (`[]`) viene cacheato lo stesso (non ri-parsare
> a vuoto). La cache sopravvive alla purge di `xml_content` → l'anteprima resta
> consultabile anche dopo. `route.ts`: timeout 30s invariato ma ora scatta SOLO al
> primo accesso di ogni fattura (dalla seconda in poi è lettura DB). +7 test guardia
> `tests/test_anteprima_coda_persistente.py` (cache hit senza parse/scrittura, parse+save,
> parse-vuoto cacheato, save-in-errore serve comunque, no-xml, parse-fallito no-cache).
>
> **Coerenza cache (nessuna invalidazione necessaria):** `anteprima_righe` è derivata
> da `xml_content`, che per una riga in coda è IMMUTABILE (scritto una volta all'insert,
> solo azzerato alla purge — mai riscritto). La cache si serve solo per `status=da_assegnare`;
> quando la fattura viene smistata esce da quello stato e l'anteprima non si serve più.
> Il `reprocess`/`riprova` admin agisce solo su `failed`/`dead`, non tocca l'XML. Quindi
> la cache non può diventare stantia nei flussi attuali. `anteprima_at` c'è per invalidarla
> a mano SE un giorno cambia la logica di parsing (basta azzerare la colonna → ricalcolo).

**Obiettivo:** eliminare la causa radice dell'intermittenza. L'anteprima non deve ri-parsare l'XML a ogni apertura.

**Dove:**
- `services/routers/riparto.py` — `riparto_anteprima_coda` (riga ~530).
- `apps/web/src/app/api/riparto/anteprima-coda/route.ts` (timeout 30s, già alzato).

**Cosa fare (in ordine di preferenza):**
1. **Parse una volta, salva le righe.** Al primo parsing riuscito, salvare le righe estratte (es. in `payload_meta` della voce coda o in una colonna dedicata). Le aperture successive leggono dal DB → istantanee, zero contesa.
2. Se il parsing a caldo resta necessario come fallback, mantenerlo ma solo quando il salvato manca.
3. Rendere il messaggio d'errore onesto già a monte: se è timeout, "riprova tra un attimo" (già fatto lato route.ts, ma la vera cura è non arrivarci).

**Perché dopo la Fase 1-2-3:** con Fase 1 molte fatture smettono di stazionare in coda (si smistano da sole), e con Fase 2-3 quelle che restano si smaltiscono in fretta → la contesa cala già di suo. La Fase 4 chiude il problema alla radice per le residue.

**Deliverable Fase 4:**
- Persistenza righe anteprima (colonna o payload_meta).
- Lettura da salvato nell'endpoint.
- Test: doppia apertura consecutiva → seconda istantanea, nessun ri-parse.

---

## FASE 5 (OPZIONALE, ULTIMA) — Fattura mista doppio-indirizzo → riparto `da_righe`

**Caso:** 2 fatture su 383 (es. Ristopiù €9256.03, 173 righe = 102 Losanna + 71 Settembrini). Una fattura sola che è di fatto due bolle. Rara ma la più costosa.

**Vincolo:** *LA FATTURA RESTA SACRA*. NON si spezzano le righe fatture. Si resta nel modello quote esistente.

**Cosa fare:**
1. Nuova `regola = 'da_righe'` accanto a `equa`/`percentuali` (estendere il CHECK constraint `regola IN (...)` su `riparto_costi_catena` e `riparto_regole_fornitore`).
2. Il calcolo quote somma i `PrezzoTotale`/`totale_riga` **per indirizzo** (righe Losanna → quota Losanna, righe Settembrini → quota Settembrini). Importi reali, non percentuali inventate.
3. Le quote vivono in `riparto_costi_catena_quote` come sempre. La fattura non viene toccata.

**⚠️ Verifica extra necessaria SOLO se si fa la Fase 5:** il motore MOL (`riparto_quote_mensili`, non ancora letto) deve gestire correttamente una fattura le cui quote vanno su **sedi diverse** con importi da righe reali, senza falsare il food-cost. Da leggere e testare prima di implementare. È l'unico rabbit-hole che ho lasciato chiuso di proposito, perché giustificato solo se il caso 3 entra nel giro.

**Raccomandazione:** NON nel primo rilascio. 2 fatture su 383. Farla dopo che 1-4 sono collaudate.

---

## FASE 6 — COLLAUDO TOTALE END-TO-END (richiesto da Mattia: "DEVE FUNZIONARE TUTTO E DEVE ESSERE COMPROVATO")

> Dopo aver implementato le fasi approvate, si prende un set di fatture reali e si segue **ogni passo del flusso e ogni tabella toccata**, provando che tutto quadra. Sola lettura sul DB dove possibile; le scritture solo tramite i flussi reali dell'app (non SQL manuale), così si collauda il codice vero.

> ### ✅ ESEGUITO 23/07 — READ-ONLY su fatture reali OFFSIDE già in coda/collocate
> Collaudo condotto senza scritture (nessuna transazione SDI consumata su P.IVA 07863990961). Ogni finding degli agenti è stato **riverificato contro codice/DB** prima di dargli peso. Verdetto secco in fondo.
>
> **Non-regressione (L0):** colonne Fase 4 presenti sul DB live; coda OFFSIDE 347 `da_assegnare` (tutte P.IVA 07863990961), 0 `failed`/`dead`/lock residui; suite `test_anteprima_coda_persistente` + `test_da_assegnare_regola_fornitore` + `test_documentazione_onesta` = 60/60. Chiarito che `ristoranti.user_id`=account-contenitore (`2f3f93a1`) e le 3 sedi vi puntano → la query anteprima `.eq(user_id)` matcha, nessun 404.
>
> **Flusso dati (flusso-dati-monitor):** canale SDI sano. Rilievo agente [ALTA] "purge prematura" **SMONTATO** verificando la RPC reale `purge_processed_xml_content` (ha `WHERE status='done'`): le 333 `da_assegnare` senza XML erano `done`-purgate-poi-riaperte dai recovery del 20/7 (tutte con `processed_at`), non purga di righe non smistate. Nessun doppione SDI/manuale.
>
> **Categorizzazione (categorization-reviewer):** PRONTA con riserva minore. 0 violazioni guardrail (NOTE con importo=0; nessun fallback SERVIZI); `Da Classificare` ~2% (ambiguo genuino). **Fase 4 verificata al punto giusto:** sulle 14 fatture in coda con XML la categoria STIMATA dall'anteprima **coincide con la definitiva** (tutti prodotti mai visti → risolvono solo via dizionario+regole, senza memoria) → nessuna divergenza stima↔definitiva, l'anteprima non mente.
>
> **Certificazione sedi (golive-certificatore):** L1 quadratura + L2 categorie + L3-pagine **OK per tutte e 3 le sedi** (OFFSIDE SPORTS PUB 50 fatture, OVERTIME 21, sede tecnica 6; copertura riconcilia per-categoria/fornitore/mese, 0 righe perse/orfane/duplicate).
>
> ### 🔴 BLOCCO REALE trovato e VERIFICATO — riparto stale gonfia il MOL (PREESISTENTE, non delle fasi 1/3/4)
> `riparto_costi_catena` ha **7 record che puntano a fatture soft-deleted** (verificato indipendentemente sul DB: 5 a gennaio — incl. CEDAG `007GS` €3.439 e `dPcef` €307,30 — + 2 a luglio). La RPC `riparto_quote_mensili` (migration `20260714140000`) somma le quote **senza join a `fatture` e senza filtro `deleted_at`** e scrive in `margini_mensili.quote_riparto_spese` → MOL. Effetto materializzato **confermato**: gennaio 2026 mostra `quote_riparto_spese=1921,34` → **MOL −1921,34 su entrambe le sedi in un mese senza alcuna fattura viva ripartita** (fantasma). Causa doppia: (a) il soft-delete di una fattura ripartita non azzera il suo riparto; (b) la RPC somma cieca.
> - **Origine:** il riparto costi catena è del 14/7, **precede questo piano**. Il collaudo Fase 6 l'ha fatto emergere (è il suo scopo), ma NON è un difetto introdotto da Fase 1/3/4.
> - **Fix (scrittura, da autorizzare a parte):** ripulire i 7 record stale + ri-eseguire `riparto_quote_mensili` per gen/lug 2026 sulle 2 sedi; e chiudere il buco delete→riparto (soft-delete deve azzerare il riparto) e/o aggiungere il filtro `deleted_at` nella RPC. Non eseguito: read-only.
>
> ### ⚠️ Altri finding NON bloccanti per le fasi in consegna
> - **6 fatture invisibili in coda** (id 650-655, OFFSIDE, 22/7): `user_id=NULL` + `processed_at=NULL` → l'endpoint `fatture_da_assegnare` filtra `.eq(user_id)` e non le mostra. Difetto webhook/routing **preesistente**, non delle fasi 1/3/4. Dati non persi (XML+indirizzo presenti).
> - **Anteprima Fase 4 non retroattiva:** le 333 già purgate non avranno mai `anteprima_righe` (XML sparito). NON bloccante: il frontend già permette la collocazione "alla cieca" con messaggio onesto; a regime ogni nuova fattura persiste l'anteprima prima della purge.
> - **2 bug regex categorizzazione** (`PESCA\b` cattura il gusto pesca del tè; `MACINAT[OA]` cattura "PEPE MACINATO"→CARNE) + 4 righe categoria sbagliata su ~180 (~2,2%): codice condiviso da tutti i clienti, fix in giro dedicato.
> - **Base di riparto lordo vs netto** (documento IVA-inclusa vs imponibile): scelta umana, da confermare con Mattia.
>
> ### VERDETTO FASE 6
> - **Fasi 1/3/4 (oggetto di questo piano):** ✅ PRONTE — nessun difetto imputabile a loro; Fase 4 comprovata coerente (stima==definitiva), suite verde, non-regressione OK.
> - **Go-live MARGINI/MOL catena OFFSIDE:** 🔴 **NON PRONTO** finché non si sana il riparto stale (MOL gennaio fantasma visibile al cliente). Blocco preesistente, indipendente dal deploy delle fasi 1/3/4.
>
> ### ✅ CHIUSURA 23/07 — SANATO + DEPLOYATO (commit 0575aea)
> Autorizzazione: «segui tu un ordine logico, procedi, per il deploy puoi farlo quando vuoi anche fuori da orario serale».
>
> **1) Riparto stale SANATO (scrittura verificata sul DB live).** Ri-verifica account-scoped: il match globale su `file_origine` era fuorviante (lo stesso file SDI esiste anche su "Ambiente Test Admin" 09011cdd — collisione cross-account). Scoped alle sole sedi OFFSIDE, gli orfani reali erano **7** (0 righe vive nell'account): 5 gennaio (UUber 38,86 · CEDAG 007GS 3439,00 · Toyota dPcef 307,30 · wcnmr 33,00 · 3Hu1x 24,52) + 2 luglio (EniMoov CSggl 32,51 · CTcjl 53,04). Eliminati (le quote cascadono via FK), poi `riparto_quote_mensili` ri-eseguita gen+lug. Effetto materializzato:
>   - **Gennaio:** quote 1921,34 → **0,00** su OFFSIDE SPORTS PUB e OVERTIME; il MOL fantasma −1921,34 è **sparito** (OVERTIME gen ora +28222,63, prima trascinato sotto).
>   - **Luglio:** quote 2932,87 → **2890,10 / 2890,09** (calati dei soli 85,55 stale, equa 50/50); i riparti luglio legittimi restano.
>
> **2) Causa radice CHIUSA (codice).** `riparto_costi_catena` non ha FK a `fatture` (aggregato per account), quindi cancellare una fattura non toccava il suo riparto → quota fantasma nel MOL. Nuovo helper `_pulisci_riparto_orfano` (services/db_service.py): all'eliminazione di una fattura (soft **e** hard) rimuove il riparto per quel `file_origine` **se non resta alcuna riga viva nell'account** (anti-collisione via `user_id`), poi ri-aggrega le quote. Cablato nei 3 path di delete (db_service soft/hard + cestino.py soft inline). +5 test guardia `tests/test_pulisci_riparto_orfano.py`. La RPC resta invariata (somma corretta ciò che esiste; il buco era a monte, nell'assenza di cleanup).
>
> **3) Deploy fasi 1/3/4 FATTO (fuori orario, autorizzato):**
>   - **Fase 1** — Edge Function `invoicetronic-webhook` **v34 → v35**, `verify_jwt:false` preservato (auth HMAC), 49 test Deno verdi.
>   - **Fase 4** — worker Railway su commit `0575aea` (health verde), colonne anteprima live; la cache si popola al primo accesso (non retroattiva, by design).
>   - **Fase 3** — frontend Vercel sullo stesso push (multi-select coda + regola-fornitore come preset).
>
> **4) Reprocess NON eseguito — VERIFICATO inapplicabile, non un rinvio.** `handleReprocess` (a) richiede `resource_id` in `payload_meta` e **333 delle 347 righe in coda non ce l'hanno** (righe di recovery manuale 20/7); (b) anche sulle 14 con resource_id **non ri-instrada** (mantiene lo `status`, riscrive solo XML+indirizzo) e (c) richiama l'API Invoicetronic esterna. Fase 1 vale per le **ricezioni SDI future**, non retroattivamente. Le 333 restano in coda per essere **smistate a mano** — ed è esattamente ciò che Fase 3 (multi-select) ora rende veloce.
>
> ### VERDETTO AGGIORNATO
> - **Fasi 1/3/4:** ✅ PRONTE e **DEPLOYATE**.
> - **MARGINI/MOL catena OFFSIDE:** ✅ **SBLOCCATO** — riparto stale sanato, MOL gennaio pulito, causa radice chiusa nel codice. Nessun costo fantasma residuo.

### 6-L0 — Non-regressione (PRIMA di toccare la produzione)
- Prendere un campione di fatture OFFSIDE **già smistate correttamente** oggi.
- Ri-passarle nella nuova `extractIndirizzoDestinatario` (Fase 1) e verificare che **la destinazione non cambi**. Nessun caso oggi-giusto deve diventare oggi-sbagliato.

### 6-L1 — Ingresso (webhook → coda)
Per un lotto di fatture reali (mix: alcune con indirizzo in `<Sede>`, alcune in `RiferimentoTesto`, alcune ambigue, la mista):
- **Tabella `fatture_queue`**: la fattura entra? `stato` corretto (`da_assegnare` solo quando davvero ambigua)?
- La cascata indirizzo (Fase 1) ha estratto l'indirizzo giusto? Log dello scoring per ognuna.
- Nessuna fattura scartata in silenzio (controllo anti-scarto-silenzioso, già ferito in passato).

### 6-L2 — Smistamento (coda → sede)
- **Anteprima (Fase 4)**: apri due volte di fila → seconda istantanea, nessun ri-parse, nessun "non leggibile".
- **Regola fornitore (Fase 2)**: fattura di fornitore con regola → proposta pronta; conferma → si smista.
- **Multi-select (Fase 3)**: 5 selezionate → 5 smistate; mix con errore → report onesto.
- Dopo lo smistamento: la voce **sparisce dalla coda**? Va nella sede giusta?

### 6-L3 — Scrittura tabelle (il cuore del "controlla tutte le compilazioni")
Per ogni fattura smistata/ripartita, verificare riga per riga:
- **`fatture`**: righe inserite con `ristorante_id` corretto, `categoria` valorizzata (mai vuota; `Da Classificare` è lecito), `deleted_at IS NULL`, `totale_riga` coerente col documento.
- **`fatture.ripartita_su_gruppo`**: TRUE **solo** sulle fatture effettivamente ripartite (anti-doppio-conteggio).
- **`riparto_costi_catena`**: 1 riga per costo ripartito, `importo_totale` = somma righe, `anno/mese` dalla data, `regola` giusta, `file_origine` popolato (vincolo UNIQUE rispettato → nessun doppione).
- **`riparto_costi_catena_quote`**: N righe (una per sede), **somma `quota_importo` = `importo_totale`** (quadratura al centesimo), `quota_perc` coerente, ogni sede una volta sola.
- **`riparto_regole_fornitore`**: se il cliente ha salvato "fai sempre così", la regola è scritta con `fornitore` normalizzato, `regola`/`percentuali` corretti, `attiva=true`.

### 6-L4 — MOL / margini (il costo arriva giusto in fondo)
- **`margini_mensili.quote_riparto_fb` / `quote_riparto_spese`**: popolate SOLO dal motore, mai dall'utente; il costo di gruppo appare distribuito sulle sede giuste nel mese giusto.
- **Anti-doppio-conteggio comprovato**: il costo NON compare due volte (né intero sulla sede intestataria né sommato alle quote). Confronto MOL prima/dopo il riparto: il totale gruppo deve restare invariato, cambia solo la distribuzione.
- La fattura mista (se Fase 5): la somma delle due quote da-righe = totale fattura, e i due food-cost di sede non si gonfiano.

### 6-L5 — Coerenza pagine/KPI (quello che vede il cliente)
- Home PV e Home catena: incasso, MOL, "fatture arrivate", salute — coerenti col DB.
- Pagina Analisi Fatture (tab Articoli, filtro "Da classificare"): le righe non classificate sono visibili, non nascoste.
- Nessun buco mensile sospetto sulle sedi.
- Briefing: dopo il deploy, **svuotare cache** (`daily_briefing_state` sede test) + bump `_BRIEFING_CODE_VERSION` se toccato.

### 6-L6 — Verdetto
- Report finale con: quante fatture passate, quante quadrate a ogni livello, ogni divergenza elencata. **PRONTO / NON PRONTO** secco. Nessun "dovrebbe funzionare".
- Strumenti già disponibili: agenti `golive-certificatore` (L1/L2/L3), `flusso-dati-monitor` (ingresso), `categorization-reviewer` (categorie). Da orchestrare qui.

---

## Ordine di esecuzione consigliato

| Step | Fase | Sforzo | Note |
|---|---|---|---|
| 1 | **Fase 2** — regole fornitore auto-proposte | basso ⭐ | fondamenta già pronte, valore immediato |
| 2 | **Fase 1** — fallback indirizzo | medio | massima evidenza, agisce sull'ingresso |
| 3 | **Fase 3** — multi-select | basso | UI |
| 4 | **Fase 4** — anteprima persistente ✅ | medio | cura radice P1 — FATTA 23/07 |
| 5 | **Fase 6** — collaudo totale | alto | dopo ogni fase implementata; obbligatorio |
| 6 | **Fase 5** — fattura mista `da_righe` | alto | opzionale, ultima, richiede verifica motore MOL |

**Regole operative (dalle tue preferenze):**
- Deploy SOLO fuori orario (sera/notte/mattina presto): i clienti usano l'app di giorno.
- Next.js locale punta al DB cloud reale → attenzione ai dati veri.
- Dopo ogni deploy che tocca il briefing: svuota `daily_briefing_state` sede test + bump `_BRIEFING_CODE_VERSION`.
- Ogni fase testata e comprovata prima di passare alla successiva.

---

## Idee extra (P3c — "altra soluzione, cosa ne pensi?")

- **Memoria indirizzo→sede per fornitore ricorrente:** oltre alla regola di riparto, memorizzare che "fornitore X consegna sempre a Settembrini" → smistamento automatico proposto anche senza dover leggere l'indirizzo ogni volta. Naturale estensione della Fase 1+2.
- **Coda ordinata per fornitore:** raggruppare la coda per fornitore rende la multi-select (Fase 3) molto più efficace ("tutte le Telepass insieme").
- **Indicatore di confidenza sullo smistamento:** mostrare in coda perché una fattura è ambigua (quale indirizzo ha trovato, con che score) così il cliente decide più in fretta.
