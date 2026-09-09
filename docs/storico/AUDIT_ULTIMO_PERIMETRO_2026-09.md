# L'ultimo perimetro — cosa resta da controllare

> **A cosa serve questo file.** È **l'unico documento di audit vivo**. Sostituisce
> i quattro del ciclo 2026-09 (stato, storico, contatore, Fable), archiviati il
> 07/09/2026 in [`docs/storico/audit-2026-09/`](../docs/storico/audit-2026-09/).
> Non racconta cosa è stato fatto — quello sta nell'archivio. Dice **cosa non è
> mai stato guardato**, e perché proprio quello.

**Aperto il 07/09/2026, riscritto lo stesso giorno dopo una seconda misura.** La
prima stesura aveva scelto due punti dentro `scripts/` e `tools/`. Rimisurando,
uno dei due file non è nemmeno nel repo, e sopra entrambi è emersa un'area più
grande e più esposta: **la logica SQL dentro il database**, che nessun ciclo ha
contato e nessun test ha mai eseguito. La selezione qui sotto è quella seconda.

---

## Da dove riparte la prossima sessione

**Stato al 08/09/2026.** Punti 1 e 2 chiusi e spediti (`origin/main` a
`e3f59ff`, CI verde, worker in produzione sul commit giusto). **Punto 3 chiuso in
locale, NON ancora spedito**: `/code-reviewer` verde, migration **applicata al DB
live e verificata su `pg_proc`** (una sola firma, a 8 argomenti, `SECURITY
DEFINER`, `anon`/`authenticated` senza EXECUTE), snapshot riallineato nello
stesso commit. Suite **13.071 verdi + 119 SQL**.

**SPEDITO il 08/09**: `origin/main` è a `5acd711`, CI verde (Tests, Requirements
Consistency), Railway ridispiegato. Il push ha portato 7 commit: i 6 della
sessione del Punto 3 più `5acd711` della sessione di comando (documentale —
cifre di CLAUDE.md ri-misurate e i quattro prompt del ciclo archiviati).
✅ **Worker verificato**: `/health` risponde `commit: 5acd711d9641` — la
produzione gira sul commit giusto (controllato dalla sessione di comando alle
12:15, che le autorizzazioni ce l'aveva).

**In coda dopo il push, non spediti** (`24b0ae0` + il commit documentale di
questa passata): il marker della review scritto dall'agente solo a verdetto
verde, il comando `/code-reviewer` allineato al profilo che lo contraddiceva, la
allowlist delle impostazioni, e un presidio sulla paginazione provato per
mutazione — tre modifiche ferme nel working tree dal 4, 5 e 7 settembre,
complete ma mai committate. Più questa passata di coerenza sulla documentazione.

### BL-1 e BL-2 chiusi — 08/09/2026, sera

**I due residui delle review dei Punti 2 e 3 sono chiusi con presidio provato
per mutazione.** Punti 2 e 3 passano da «chiusi sul codice» a **chiusi con
review verde** (la review sul cumulativo A1+A2 è il passo successivo, non
questa riga).

**BL-2 — snapshot allineato** (`e5efb21`). Delle quattro funzioni toccate dai
Punti 2 e 3, **tre coincidevano già col live**: verificate una per una con
`pg_get_functiondef`, non assunte — `aggiorna_categoria_fatture_attribuita`,
`aggiorna_categoria_prodotto_attribuita`, `_azzera_attribuzione_categoria`. La
sola divergenza di corpo era `fn_log_category_change`: la costante `c_uuid`
dichiarata sul live, inlineata come regex nei due usi nello snapshot. Più la
posizione di `_azzera_attribuzione_categoria`, che stava in cima al blocco prima
delle IMMUTABLE ed è stata spostata fra le plpgsql, dove la mette l'`ORDER BY`
dello script. La prova che l'ordine regge non è la lettura: è che il DB di test
si monta ancora, **119 test SQL verdi**.

L'allineamento è a mano — `SUPABASE_DB_URL` non è disponibile — e
**l'intestazione dello snapshot ora lo dichiara**: la regola «non modificare a
mano» è stata sospesa sapendone il costo, non violata per distrazione. Chi
arriva dopo lo legge nel file, non in un verbale.

Corretta la data dello snapshot (`2026-09-09` → `2026-09-08`: la fixture la usa
come taglio per le migration da ri-applicare) e le altre **13 occorrenze di
«09/09» in 7 file**, ri-contate con `grep -o` prima di toccarle. Il nome della
migration `20260909090000` **non** è toccato: è applicata al live con quel nome.

Provato per mutazione: neutralizzando la guardia (`NOT p_salta_arbitrate` →
`true`) **in entrambi i file** — la fixture ri-applica la migration sopra lo
snapshot, mutarne uno solo non misura niente — muoiono i 3 test attesi di
`tests/test_sql_registro_correzioni.py`.

**BL-1 — la paginazione di `categoria_batch` ha una rete** (`e93d6ff`). Due
test in `tests/test_fatture_categoria_guardrail.py`, uno per ramo (riga 913
normale, riga 930 NOTE E DICITURE). Il fake del file onorava già `.range()` ma
**restituiva tutto quando non veniva chiamato**, ed era proprio questo a rendere
il test inutile. Ora tronca a 1000 come PostgREST, e i test possono fallire.
Provati per mutazione **per numero di riga** (`fetch_all` compare 4 volte nel
file): 913 uccide solo il test del ramo normale, 930 solo quello del ramo NOTE.
Ogni riga ha il suo presidio, isolato.

Il margine non è teorico: sul live una sola descrizione su una sede è a **930
righe** (`SALMONE 5-6`, ri-misurata l'08/09).

**Suite intera dopo i due commit: 13.192 verdi, 44 skip, 0 rossi.**

**Review sul cumulativo: 🟢 verde** (`2105d44..e93d6ff`), nessun blocco. Il
reviewer ha ri-provato per mutazione entrambi i presidi e ri-confrontato i 4
corpi col live con `difflib`: nessuna divergenza residua. Quattro rilievi non
bloccanti, uno dei quali **fondato e corretto subito** (`5b2d58d`): N1 —
`_azzera_attribuzione_categoria` non era all'ordine canonico. L'ho verificata
riproducendo l'`ORDER BY` di `Q_FUNZIONI` sul catalogo live invece di
accettarla: la funzione va **in 4ª posizione**, dopo `normalizza_indirizzo_match`
e **prima** di `accoda_upload_ambiguo` — la collation ignora l'underscore, e
`_azzera` ordina come `azzera`, dopo `aggiorna` ma prima di `accoda`. Innocuo a
runtime (nessuna `LANGUAGE sql` la chiama, misurato), ma un file allineato a
mano vale finché è quello che lo script produrrebbe.

Gli altri tre non si chiudono qui, e sono nominati per non perderli: **N2** —
`genera_schema_snapshot.py --check` non gira in CI, ed è il motivo per cui
queste divergenze arrivano fin qui; va valutato **quando la URL sarà
disponibile**, oggi non è costruibile. **N3** — i commit non sono su
`origin/main`: la CI non ha visto questo lavoro, il verde è locale (è la policy
del progetto, non una dimenticanza). **N4** — l'ordine sbagliato di N1 era
innocuo solo finché nessuna `sql` chiama quella funzione.

> **Il registro non ha ancora visto una riga attribuita vera.** Misurato oggi:
> **4.132 righe totali**, ultima scrittura **2026-09-03 14:52**, e **0 righe con
> `source='worker_coda'`**. La prova che l'attribuzione funziona in produzione è
> la prima riga che compare con quel `source`: va **guardata**, non assunta. Il
> codice è chiuso, il campo no.

---

### SPEDITO — 08/09/2026, 20:51 UTC (22:51 italiane)

`origin/main`: `5acd711` → **`13d188e`**, **11 commit** (8 miei, 3 di altre
sessioni: `24b0ae0`, `2105d44`, `77bdbaa`). Coda a zero.

- **Railway**: worker ridispiegato in ~1 minuto, `/health` risponde `200` in
  0,9s sul commit `13d188e73fa4`, `upload_ai: on`. Coda fatture sana: 651 `done`,
  12 `da_assegnare` (attesa di P.IVA, stato precedente al deploy, non un guasto).
- **Vercel**: **non è partito, ed è corretto** — zero file in `apps/web/**`.
- **DB**: nessuna azione richiesta, la migration era già applicata.
- **Rischio reale del deploy: nullo sul comportamento.** Nei tre file di runtime
  toccati (`services/db_service.py`, `scripts/ricategorizza_sede*.py`) il
  confronto **AST** prima/dopo dà codice identico: cambiano solo commenti e
  docstring. Tutto il resto sono test, snapshot e documentazione.
- **CI verde su `13d188e`**: Tests ✅ (4m32s), Requirements Consistency ✅ (8s).
- Gate pre-push: `/code-reviewer` **verde**, con verifica indipendente che i 75
  corpi funzione dello snapshot coincidono col live (75/75) e che la firma sul
  DB è unica.

> **Due cifre sono invecchiate durante la sessione** e le ho corrette a ridosso
> del push (`13d188e`): gli incassi erano 1.074 giornate con ultimo il 7/9, alla
> ri-misura delle 20:45 erano **1.075** con ultimo l'**8/9** — un cliente ha
> caricato mentre lavoravo. È il motivo per cui le cifre si ri-misurano quando si
> scrivono, non si ereditano.

---

### Il DB entra nel contatore — 08/09/2026

**Le 8 funzioni SQL di Livello 1 sono provate** (`1df7678`). 36 test in
`tests/test_sql_funzioni_pagina.py`, che le **eseguono** su un Postgres vero
montato dallo snapshot: `articoli_da_fatture`, `gruppo_spesa_pivot`,
`gruppo_tag_trend`, `gruppo_tag_fornitori`, `gruppo_tag_descrizioni`,
`gruppo_salute_componenti`, `chat_top_categoria_fornitore`,
`chat_usage_check_and_log`. Test SQL totali: **119 → 155**.

**17 di cui 8 provate.** Restano scoperte le 9 di Livello 2, per scelta di
perimetro: `admin_ai_mensile`, `admin_consumi_mensili`,
`admin_conteggio_fatture`, `admin_fatture_per_mese`, `get_ai_costs_summary`,
`get_ai_costs_timeseries`, `get_ai_recent_operations`, `increment_ai_cost`,
`track_ai_usage_event`. Sbagliate danno un numero storto a chi gestisce il
prodotto, non a chi lo usa.

**Provate per mutazione: 13 mutanti, 13 uccisi.** Mutati **per numero di riga
dentro la funzione giusta** — lo stesso `deleted_at IS NULL` vive in 10 corpi, e
per pattern avrei misurato un'altra funzione. Backup preso prima del primo,
md5 verificato identico alla fine.

**Quattro funzioni avevano già dei test, e nessuno le eseguiva.**
`test_gruppo_tag_note_credito.py`, `test_gruppo_spesa_pivot_quote.py`,
`test_gruppo_completezza_override.py`, `test_da_classificare_sql_allineato.py`
mockano il client Supabase o leggono il **file** della migration. Difendono cose
vere, ma un errore dentro il corpo SQL passava intatto sotto tutti quanti. La
docstring di `test_gruppo_tag_note_credito.py` dichiarava «le RPC non sono
esercitabili da pytest»: vero fino al 07/09, falso dal giorno dopo — corretta
(`a76e82b`).

**Due cose misurate che il prompt non prevedeva:**

1. **Le tre RPC della pagina Tag non concordano su `Da Classificare`.**
   `gruppo_tag_descrizioni` la esclude (regola di dominio #1);
   `gruppo_tag_fornitori` e `gruppo_tag_trend` **no**. Una descrizione non
   classificata sparisce dall'elenco dei tag, ma se il tag esiste per altre
   righe la sua spesa entra nel dettaglio fornitori e nel grafico. Il test fissa
   il comportamento di oggi e **non dichiara chi ha ragione**: è una decisione
   di prodotto, e va portata a Mattia.
2. **Un ramo di `chat_top_categoria_fornitore` è irraggiungibile.** Il
   `COALESCE(NULLIF(TRIM(categoria), ''), 'Altro')` non può scattare: il
   constraint `fatture_categoria_not_empty_chk` rifiuta la categoria vuota.
   Scoperto perché la prima stesura del test seminava quel dato e **il DB l'ha
   respinto** — non è un difetto, è codice difensivo su un caso impossibile.

Documentato anche il **limite chat che azzera a mezzanotte UTC** (01:00/02:00
italiane): un cliente che scrive all'00:30 consuma ancora la quota di ieri.
Divergenza nota e **non decisa** dal 07/09: il test la fissa, non la cambia.

| Perimetro | Prima | Ora |
|---|---|---|
| **Logica SQL dentro il DB** | 75 funzioni, mai nel contatore | **75 funzioni: 20 eseguite da un test** (12 già coperte + le 8 di oggi), 9 di staff dichiarate scoperte, **22 di servizio** (prefissi `update_*`, `set_*`, `fn_*`, `purge_*`, `trg_*`: trigger di orario e job di pulizia, non muovono numeri), **24 non ancora classificate**. 20+9+22+24=75 |

> **Le «35 di servizio» del prompt erano una stima ereditata, non una misura.**
> Contandole per prefisso sullo snapshot sono **22**, e le funzioni non ancora
> classificate sono **24**, non 11. Fra queste ce ne sono di vive che muovono
> dati veri — `dashboard_stats_aggregata`, `soft_delete_fatture_massivo`,
> `crea_riparto_con_quote`, `sostituisci_quote_riparto`, `assegna_fattura_a_sede`,
> `gruppo_tag_analisi`, `sync_margini_mensili_from_ricavi` (quest'ultima già
> coperta indirettamente dai test del riparto) — quindi «17 funzioni vive» era
> il perimetro di quel prompt, **non l'inventario del database**. Chi riapre il
> tema parta da qui, non dal 17.

---

### La review della Parte B, e i suoi findings chiusi — 08/09/2026, sera

**Verdetto: 🟢 verde**, nessun blocco. Il reviewer ha provato **37 mutanti su
righe che io non avevo toccato**: 29 uccisi, **8 sopravvissuti**. Non erano
difetti di ciò che avevo chiuso, ma comportamenti che i test fingevano di
coprire. **Li ho chiusi tutti**: 7 nuovi test, e i 13 mutanti corrispondenti
ora muoiono tutti (verificati uno per volta, snapshot ripristinato per md5).

Il più grave era **l'isolamento fra clienti**: 7 funzioni potevano perdere il
filtro `ristorante_id`/`user_id` **senza un solo test rosso**. Nessuna RLS le
copre — `auth.uid()` è sempre NULL e ogni client usa `service_role` — e due
(`articoli_da_fatture`, `chat_top_categoria_fornitore`) non sono nemmeno
`SECURITY DEFINER`. La causa era una sola: **le seed piantavano un unico
tenant**, quindi neutralizzare il filtro non cambiava nessun risultato. Ora ogni
test semina anche un secondo cliente con righe sulle stesse descrizioni.

Due cose imparate mentre chiudevo, che valgono più dei test:

1. **Il rumore va messo dove discrimina.** Prima ho seminato righe estranee
   anche sulla sede sotto test: 10 test sono caduti **su un comportamento
   corretto** (le `gruppo_*` filtrano per sede, non per utente — una riga altrui
   su quella sede ci entra a ragione). E per `articoli_da_fatture`, che filtra
   su `user_id` **e** `ristorante_id`, serve il caso in cui **solo uno dei due**
   discrimina: con filtri ridondanti il mutante sopravvive comunque.
2. **Due mutanti sopravvissuti non sono un buco.** In
   `gruppo_salute_componenti` i due `WHERE ... = ANY(p_ristorante_ids)` dentro
   le CTE sono **ridondanti**: è il `LEFT JOIN unnest(...) ON f.rid = r` a
   selezionare le sedi. Verificato **sui dati veri** (2.137 e 1.258 righe: stesso
   risultato con e senza il WHERE), non dedotto dal codice. Il commento nel test
   lo dice, così il prossimo non ci ripassa.

**La divergenza dei tag ha impatto reale, misurato sul live**: **12 chiavi
distinte** su 5 sedi (16 coppie chiave×sede: la stessa descrizione colpisce più
sedi), 33 righe, **3.052,27 €** che spariscono dall'elenco tag ma restano nel
dettaglio fornitori e nel grafico. La prima stesura di questa riga diceva «16
chiavi»: erano le coppie, non le chiavi — corretto dopo la ri-misura. Il caso peggiore è `COMMISSION` di **Sushiland
San Giuliano**: 8.354 € nel grafico contro 5.585 nell'elenco, **33% di scarto**.
Oggi nessuno dei 3 tag realmente creati dai clienti è fra quelli colpiti — quindi
0 € visibili adesso — ma basta che quel cliente tagghi una delle 16 chiavi.
**Decisione per Mattia**, non mia: allineare le tre RPC significa cambiare totali
già visti.

Test SQL: **119 → 164**. Suite intera: **13.237 verdi, 44 skip, 0 rossi** (13.228 in `tests/` + 9 in `legacy_streamlit/`: se lanci solo `tests/` vedi il primo numero, ed è la differenza che fa sembrare discordanti due misure entrambe giuste).

**Review finale sul cumulativo della sessione: 🟢 verde**, nessun blocco. Le due letture che avevo scoperto sbagliando sono state **confermate per misura**, non per lettura del codice: il rumore va sulla sola sede estranea (nessun endpoint accetta `ristorante_ids` dal client — la lista nasce dal token, `services/routers/gruppo.py:672-681`), e i due mutanti vivi in `gruppo_salute_componenti` sono davvero codice ridondante (`EXCEPT` bidirezionale sul live: 0 righe da entrambi i lati).

---

**Chiuso il Punto 3, il ciclo dell'ultimo perimetro è finito.** Questo file va
spostato in `docs/storico/` e non se ne apre un altro: da qui vale la regola
ordinaria — *quando tocchi un file, lo copri*.

> **Prompt per la prossima sessione**: `docs/piani/PROMPT_FUNZIONI_SQL_VIVE.md`
> (scritto dalla sessione di comando l'08/09, aggiornato alle 12:30). La
> **Parte A** chiude i residui dei Punti 2 e 3: lo snapshot va allineato **a
> mano** — `scripts/genera_schema_snapshot.py` richiede `SUPABASE_DB_URL`, la
> password Postgres del progetto, che **non è disponibile e non si recupera**
> (decisione di Mattia dell'08/09, presa sapendo il costo: si fa a mano, non si
> resetta la password). Il prompt spiega passo per passo come farlo senza
> rompere l'ordine di creazione delle funzioni, che non è estetica: una `sql`
> che ne chiama un'altra esige che quella esista già.
> Oggi `fn_log_category_change` non coincide col live e la
> data dichiarata è «2026-09-09» (BL-2 della review del Punto 2, ancora aperto);
> e il fix `fetch_all` di `categoria_batch` non ha un test che lo presidi (BL-1).
> La **Parte B** apre le **17 funzioni SQL vive** che nessun test esegue (8 viste
> dal cliente, 9 di staff). Suite su copia pulita di `07157be`: **13.180 verdi +
> 44 skip**, 119 SQL inclusi. Cifre di `CLAUDE.md` e di questo file allineate
> alle 11:50 dell'08/09.

> **Provata sui dati veri, in sola lettura.** Valutando la condizione della
> guardia sul live: la riga 128426 (l'involtino di VILLA GUARDIA, `reviewed_at`
> valorizzato) risulta **protetta**, mentre la 128349 (`SALMONI 5/6`, mai
> arbitrata) resta lavorabile. La guardia discrimina in produzione, non solo nei
> test.

> **Lo snapshot non è diventato tautologico.** Con l'header spostato al
> `2026-09-09` la fixture non applica più la migration sopra lo snapshot, quindi
> i test girano sul solo snapshot: verificato neutralizzando la guardia in
> **entrambe** le sorgenti — 3 test SQL rossi. È il controllo che il 07/09 era
> mancato e aveva reso tautologici tre test senza che nessuno se ne accorgesse.

> **Il push non deve più aspettare la migration, ma lo snapshot sì.** La review
> aveva trovato un blocco vero: mandando `p_salta_arbitrate` a ogni chiamata, con
> sul live solo la firma a 7 argomenti PostgREST avrebbe risposto `PGRST202` a
> **tutte** le 13 scritture esistenti, che sarebbero cadute nel fallback HTTP —
> senza attribuzione. Il registro sarebbe tornato cieco proprio per il lavoro dei
> Punti 1 e 2, già in produzione. Risolto alla radice: il parametro si manda
> **solo a chi lo chiede** (`services/db_service.py`), quindi il codice funziona
> sia prima sia dopo la migration. Resta comunque da applicare la migration e
> riallineare lo snapshot, ma non è più un vincolo d'ordine da ricordare.

> **Le due condizioni del residuo migration sono state entrambe soddisfatte**
> (erano nel verdetto `/code-reviewer` del 08/09): la migration è applicata, e lo
> snapshot è riallineato nello stesso commit. I due script CLI possono ora essere
> lanciati con l'attribuzione piena.

> **Le inerenze, misurate eseguendo.** `aggiorna_categoria_fatture` ha 11
> chiamanti applicativi più i 2 script. Verificato con `inspect.signature` che
> gli unici parametri obbligatori restano `ids` e `categoria`, e che nessun
> chiamante passa posizionali oltre al client; e simulando il payload RPC di
> ogni percorso reale (correzione_cliente, worker_coda, admin_propagazione,
> admin_classifica, post_upload, agent_notturno) che **tutti mandano 7
> parametri** e colpiscono la firma presente sul live. Solo i 2 script ne
> mandano 8. È il test `test_i_percorsi_di_produzione_restano_compatibili_con_la_rpc_a_sette_argomenti`.

> **Un test che dipendeva dall'ordine, trovato dopo la review.** La fixture del
> modulo era `scope="module"`: i patch di un test restavano attaccati al
> successivo, e `test_il_dry_run_non_scrive` falliva secondo l'ORDINE, non
> secondo il codice — da solo passava. La prima spiegazione plausibile («il
> dry-run scrive davvero») era falsa, e avrebbe portato a cercare il bug nel
> codice giusto. Fixture per-test.

> **Un test che non presidiava, trovato dalla review.**
> `test_la_scrittura_passa_dal_chokepoint_attribuito` cercava
> `"aggiorna_categoria_fatture"` nel sorgente: il nome compare due volte (import
> e chiamata), quindi **il solo import bastava** e il test restava verde
> rimettendo la scrittura diretta — misurato, 12 passed sul difetto. Riscritto:
> ora esegue `main()` con un client finto che **solleva** se qualcuno tocca
> `.table()`, e verifica `source`, `batch_id` e il flag. Il mutante ora muore.
> L'altro test su sorgente (`test_la_select_porta_le_colonne...`) è stato
> verificato e uccide il suo mutante: resta com'è.

### Cosa ha chiuso il Punto 3 (08/09)

Gli script che scrivono `categoria` non possono più sovrascrivere ciò che un
umano ha deciso, e dichiarano chi sono nel registro.

| Prima | Dopo |
|---|---|
| il precedente del 26/08 ancora vivo | riga 128426 protetta e coperta da test |
| scrittura `.update()` diretta, `db_trigger` anonimo | dal chokepoint, `source='script_ricategorizza_sede'` + `batch_id` |
| presidio = **replica** del codice (verde su ogni mutante) | il test **esegue** il modulo vero |
| `.limit(10000)` troncato a 1000 in silenzio | `fetch_all` |

**Il bug del 26/08 era vivo, e l'ho riprodotto**: la riga 128426 di VILLA
GUARDIA (`INVOLTINO VIETNAM (POLLO)`, decisa a mano come CARNE il 25/06) passata
nella pipeline dello script ne usciva `PASTA E CEREALI`. Non era un rischio
teorico: è il caso di test del presidio.

**La guardia è opt-in, e non è un dettaglio.** La correzione del cliente passa
dallo stesso chokepoint: con la guardia sempre attiva il cliente non potrebbe
più correggere due volte la stessa riga. La regola è *ciò che un cliente decide
vale per lui, non per gli altri* — chi scrive per conto d'altri si ferma, chi
scrive per sé no. Due test coprono entrambe le direzioni.

**Tre premesse del prompt smentite dalla misura**: gli script scrittori sono
**19, non 41** (il grep contava `sys.path.insert`; `catscan_freddo` e
`catscan_senza_segnale` sono read-only); quelli che scrivono `categoria` sono
**5, non 6**; e `catscan_applica.py` era **morto** — apriva un JSON inesistente,
crashava alla riga 17. Cancellato, insieme a `tools/fix_sospette_memoria_globale.py`
(cross-tenant senza filtro `user_id`, `DRY_RUN=False` committato come default:
tutte le 330 righe arbitrate erano raggiungibili da lì).

> **Il predicato non è "un umano ha deciso", è "già arbitrata".** Delle 318
> righe con `reviewed_at`: 134 `auto-review`, 92 `bonifica-fallback-23-06`, ~92
> batch admin caso per caso. Coperte tutte comunque — anche una sweep accettata
> da un admin non va riscritta di nascosto — ma la sfumatura va detta.

> **Residuo dichiarato: `admin_propagazione` non passa la guardia.**
> `services/ai_service.py:4640` scrive cross-tenant e si difende leggendo
> `prodotti_utente.classificato_da` (`_e_override_manuale`), cioè la **memoria**,
> non `fatture.categoria_fonte`/`reviewed_at`. Le 318 righe con `reviewed_at`
> non hanno una voce in `prodotti_utente` e restano raggiungibili da lì; e a
> `routers/fatture.py:977` la scrittura in memoria è best-effort, quindi una
> riga può restare protetta dalla sola `categoria_fonte`, che la propagazione
> non guarda. Fuori dal perimetro «script» di questo punto — ma è lo stesso
> lavoro, e va deciso se aprirlo. Stessa cosa per
> `scripts/_recalc_review_sushiland.py`, che scrive `needs_review` senza guardia
> e può sbloccare una riga arbitrata.

> **Il perimetro protetto crescera' da solo, ed e' voluto.** `admin_propagazione`
> (`services/ai_service.py:4640`) scrive `reviewed_at` su OGNI riga che tocca:
> da ora ogni sua esecuzione rende quelle righe intoccabili dagli script. Oggi
> non pesa — misurato il 08/09, `reviewed_by='admin-global-propagation'` non
> compare sul live: quella funzione non e' mai stata usata in produzione. Ma fra
> sei mesi il numero delle righe saltate sara' cresciuto senza che nessuno abbia
> cambiato la guardia: e' l'effetto atteso, non un difetto da investigare.

> **`IS DISTINCT FROM` e non `<>`**: le 318 righe `reviewed_at` hanno tutte
> `categoria_fonte` NULL, e con `<>` il predicato varrebbe NULL. Stessa trappola
> nel fallback HTTP, dove `.neq()` scarta i NULL: lì serve
> `or_(is.null, neq.)`, come già fa `escludi_da_verificare_margini`. Misurato:
> con `.neq()` secco la guardia bloccherebbe 39.221 righe legittime su 39.515.

**Modello: Opus.** `ultrathink` solo se si riapre una decisione di impianto —
qui l'impianto c'è già (il chokepoint attribuito), il Punto 3 lo estende agli
script.

**Prima di toccare qualsiasi cosa**, tre comandi:

```bash
python -m pytest -q -m sql          # 113 test, devono essere verdi
git log --oneline origin/main..main # commit accumulati e non ancora spediti
python scripts/check_documentazione.py
```

Se i test SQL non sono verdi, **non è un problema dei test**: o lo snapshot è in
drift rispetto al DB live, o una migration nuova non si applica sopra. La
fixture lo dice esplicitamente nel messaggio di errore.

### Cosa ha chiuso il Punto 2 (08/09)

Il registro **sa chi scrive**. Le scritture di `categoria` su `fatture` passano
da una RPC attribuita (`aggiorna_categoria_fatture_attribuita`) che imposta i GUC
letti dal trigger e li **spegne subito dopo**, nella stessa transazione.

| Prima (07/09) | Dopo (08/09) |
|---|---|
| 4.132 righe, 0 attori, 1 solo `source` | impianto attivo: la prossima scrittura è attribuita |
| nessun chokepoint (13 punti a mano) | `aggiorna_categoria_fatture` in `db_service` |
| — | 9 test SQL + 9 test Python, provati per mutazione |

**Perché l'attribuzione vive nel DB e non nel client.** Il trigger legge GUC di
sessione, e PostgREST prende una connessione dal pool a ogni richiesta: da Python
non si possono mettere `SET LOCAL` e l'`UPDATE` nella stessa transazione. La
strada "ovvia" (l'attore negli header del client) era la trappola già pagata dal
progetto — `_riallinea_auth_header` esiste per quell'incidente. Dentro una
funzione SQL, GUC e UPDATE sono per costruzione la stessa transazione.

**Convertiti**: worker della coda, propagazione admin cross-tenant, agent
notturno, post-upload, admin classifica/auto-review, e i 3 percorsi di correzione
manuale del cliente (gli unici con identità utente vera). Le scritture massive
portano un `batch_id` condiviso, così un lotto si legge come lotto.
`admin_qualita_audit_annulla` resta di proposito sul percorso diretto: azzera i
campi a NULL e la RPC fa `COALESCE` (motivo scritto nel codice).

**I 34 casi sospetti: nessun danno.** I 38 eventi erano 3 correzioni admin di
giugno (pasta ripiena 21, dolci 7, Villa Guardia 2) più 4 dell'auto-review;
tutte le righe sono finite dove dovevano, zero rimaste sbagliate. Il caso
TOPRINSE che sembrava un conflitto era un'andata-e-ritorno di 4 secondi.

> **Il code-reviewer ha trovato un bug introdotto proprio dal fix.** Per far
> passare la scrittura dalla RPC, `categoria_batch` risolveva gli id con
> `.execute()` invece di `fetch_all`: l'UPDATE sostituito non aveva limiti, ma
> PostgREST **tronca a 1000 righe senza errore**. Su una sede reale la
> descrizione `SALMONE 5-6` è già a **930 righe attive**: oltre soglia il cliente
> avrebbe letto "fatto" con le righe in più non toccate. Corretto prima del push,
> su entrambi i rami. **La lezione**: sostituire un UPDATE con select+UPDATE
> introduce un limite che l'UPDATE non aveva.

**Residuo dichiarato, non dimenticato**: la memoria delle correzioni
(`prodotti_utente`, **110 righe** di registro) resta anonima. La scrivono degli
`upsert` che non possono impostare i GUC, e da PostgREST non esiste una
transazione in cui farlo: serve una RPC che faccia l'upsert lato DB. La funzione
SQL gemella (`aggiorna_categoria_prodotto_attribuita`) è già sul live e testata.

### Cosa ha chiuso il Punto 1

I test SQL passano da **38 a 104**. Le sette funzioni che calcolano i numeri che
il cliente legge — `riparto_quote_mensili`, `sposta_fattura_a_sede`,
`sync_margini_mensili_from_ricavi`, `scadenziario_fatture_aggregate`,
`costi_automatici_mensili` e `costi_automatici_mensili_gruppo` — ora si
**eseguono** nei test invece di essere lette. Prima nessun test ne toccava una
riga. La settima, `costi_automatici_mensili_gruppo` (Sintesi di catena), non era
nell'elenco del prompt: l'ha trovata scoperta il code-reviewer.

Provate per mutazione: **30 mutanti, uno per volta, 29 uccisi**. Il sopravvissuto
è spiegato dentro il test e non è un test debole — l'esclusione di
`NOTE E DICITURE` da `costi_automatici_mensili` è ridondante dietro il CHECK che
impedisce a una nota con importo diverso da zero di esistere. Resta come seconda
cintura, se il CHECK un giorno venisse allentato.

> **Una lezione sul metodo, non sul codice.** Un mutante risultava sopravvissuto:
> mutavo la **prima** occorrenza del pattern nello snapshot, che stava in
> `assegna_fattura_a_sede` — un'altra funzione, non coperta da quei test. Il
> codice sotto prova non era mai stato toccato. Rifatto sull'occorrenza giusta, è
> morto subito. **Verificare sempre dentro quale funzione cade la mutazione.**

### La premessa che la misura ha smentito

Il prompt dava **5 funzioni per morte**. `get_distinct_files` non lo era: ha due
chiamanti veri in produzione (`services/db_service.py`,
`services/upload_handler.py`). Cancellarla in blocco avrebbe rotto la
cancellazione massiva e la deduplicazione upload.

Sotto c'era però un difetto vero. Le tre varianti rendevano ambigua la chiamata
col solo `p_user_id`: PostgREST rispondeva `PGRST203`, e in
`elimina_tutte_fatture` l'errore veniva **ingoiato** — all'utente si dichiaravano
MENO fatture di quante se ne cancellavano. E togliere la sola variante legacy
`(text)` **non bastava**: le due rimaste erano ambigue fra loro, perché il
`DEFAULT NULL` rende la 2-arg chiamabile con un argomento solo. Visto eseguendo,
sul DB di test e sul live — non deducendo.

La migration `20260907194500_elimina_funzioni_senza_chiamanti.sql` elimina sei
funzioni: le quattro morte, la `get_distinct_files(text)` (senza guardia auth,
non filtrava il cestino, e rotta di suo: `search_path` vuoto ma `fatture` non
qualificata) e il wrapper `get_distinct_files(uuid)`, ridondante. Resta
l'implementazione completa, che serve entrambi i chiamanti.

✅ **Applicata al DB live il 07/09/2026 e verificata sui dati veri.** Sulla sede
più grande (12.956 righe, ben oltre la soglia dei 1000 che attivava il difetto)
la chiamata senza sede ora risolve e ritorna 2.582 file distinti, quella con
sede 1.082. Snapshot riallineato nello stesso commit (162 righe tolte).

> **Il riallineamento ha rotto un presidio, in un modo che vale la pena sapere.**
> Tolte le varianti dallo snapshot, i test «non è ambigua» diventavano
> **tautologici**: veri anche se il presidio non avesse funzionato. E il modo di
> provarli — rimettere il wrapper nello snapshot — non misurava più niente,
> perché la migration applicata sopra lo ricancellava. Verificato neutralizzando
> il `DROP`: 3 failed, cioè misuravano la migration, non il difetto. Ora un test
> ricrea l'ambiguità **in transazione** e verifica di vederla, quindi non dipende
> da un file che un giorno sarà solo storico. **Ogni volta che si riallinea lo
> snapshot dopo un DROP, ricontrollare che i test su quel DROP mordano ancora.**

### Le due divergenze — decisione di Mattia, non un bug

Ri-misurate il 07/09/2026, entrambe confermate:

- **`data_competenza` vs `data_documento`**: dashboard, chat e spreco aggregano
  per data documento; margini e gruppo per competenza. **229 righe, 3.794,14 €,
  1 sede, 1 utente** — identico alla misura precedente.
- **Limite giornaliero chat**: `chat_usage_check_and_log` usa
  `date_trunc('day', now() AT TIME ZONE 'UTC')`, quindi azzera alle 02:00
  italiane d'estate (01:00 d'inverno). Chi chatta all'una di notte consuma la
  quota del giorno prima.

### Un test che stava per mentire

`tests/test_da_classificare_sql_allineato.py` dichiarava «7 RPC **vive**,
misurato su `pg_proc`» ma cercava quei nomi nel **testo delle migration**. Con
`gruppo_prezzi_categoria` eliminata le vive sono 6, e siccome le migration sono
storico immutabile il test sarebbe rimasto **verde dicendo una cosa falsa** —
proprio dopo l'applicazione al live, quando nessuno riguarda. Datato e spiegato.
La lista resta invariata perche' e' corretta rispetto a cio' che il test misura
davvero; resta aperto, come lavoro a se', trasformarlo in una misura su
`pg_proc` ora che `conftest_sql.py` lo consente.

### Un residuo da sapere

`tools/check_migrations.py` **non è tracciato da git**: le due voci che
chiamavano funzioni ora eliminate sono state tolte, ma la modifica resta solo su
disco e non è nel commit. Se il file venisse versionato in futuro, va rifatta.

**Il limite noto, da non riscoprire.** Lo snapshot va in drift appena si applica
una migration al live. `scripts/genera_schema_snapshot.py --check` lo
rileverebbe ma richiede `SUPABASE_DB_URL`, che il progetto non ha: oggi lo
snapshot si produce via MCP Supabase. Metterlo in CI vorrebbe dire dare alla CI
una connessione al DB dei clienti, peggio del problema. Mitigazione attuale: la
fixture applica le migration più recenti dello snapshot e fallisce rumorosamente
se non si applicano. **Quando si applica una migration al live, riallineare lo
snapshot nello stesso commit.**

---

## Perché i cicli precedenti sono chiusi

Non perché il lavoro fosse finito, ma perché **avevano finito di rispondere alla
loro domanda**. Tre cicli, tre metri diversi:

| Ciclo | Domanda | Esito |
|---|---|---|
| 2026-07 | «Ogni dimensione (Security, Bug, AI…) è stata passata?» | 10/10 chiuse, su un'app di ~103.000 righe |
| 2026-08 | «I file grandi mai letti sono stati letti?» | chiuso, §1/§2/§3b/§3c vuote |
| 2026-09 | «Quante righe dell'app ha letto qualcuno?» | 111.492 su 114.808 — ri-misurato l'08/09 a `fff50ea` (era 111.202 su 114.518 il 6/09) |

Tutte e tre le risposte sono vere. **Nessuna delle tre dice se il codice
funziona**, e nessuna ha mai guardato fuori dal perimetro che si era scelta.

> ⚠️ **L'avviso era già scritto a luglio**, e per sei settimane nessuno l'ha
> pesato: *«"10 dimensioni verdi" non vuol dire "app analizzata al 100%". Una
> dimensione è verde rispetto al perimetro che quella passata si è scelta.»*
> Questo file esiste per guardare **fuori** da quei perimetri.

---

## Le due misure di contesto, prese il 07/09/2026

### 1. Copertura reale del backend: 61%

```bash
python3 -m coverage run --source=services,utils,config,worker -m pytest tests/ -q
python3 -m coverage report --sort=cover
```

**13.028 test passati, 0 falliti.** `TOTAL 24239 stmts, 8944 miss → 61%.`

> Correzione alla prima stesura, che diceva «cosa che nessun ciclo aveva mai
> fatto». Falso: la misura esiste dall'8/8/2026 (`.coveragerc`, gate in
> `.github/workflows/tests.yml` con `--fail-under=45`, 50% misurato quel giorno).
> Quello che nessun ciclo ha fatto è **usarla come metro**: il passaggio da 50% a
> 61% non compare in nessun verbale, perché il contatore contava le righe lette.

Dove si è lavorato davvero si vede (`riparto.py` 94%, `personale_export` 96%,
`margine_service` 85%). Dove non si è lavorato, anche:

| Modulo | Copertura | Righe non eseguite |
|---|---:|---:|
| `routers/tag.py` | 35% | 135 — tocca la regola di dominio #1 |
| `routers/admin.py` | 39% | 919 — solo staff |
| `upload_handler.py` | 40% | 654 — ingresso fatture |
| `db_service.py` | 42% | 610 — layer dati di tutto |
| `auth_service.py` | 47% | 380 — login, sessioni, password |
| `fastapi_worker.py` | 52% | 1.643 |

**Questo NON è il lavoro di questo ciclo.** È il contesto: dice che la rete
esiste ed è densa dove passano i soldi. Alzare quelle percentuali è lavoro a
rendimento calante — si fa quando si tocca il file, non con cicli dedicati.

### 2. Il frontend non è recuperabile, e va detto

| Perimetro | Righe | Testabile? |
|---|---:|---|
| `.tsx` (rendering, hook, stato) | 42.293 | **No** — nessun runner npm, per scelta |
| `.ts` logica pura | 11.366 | Sì |
| di cui `lib/` con presidio | **5.247 / 6.064 (87%)** | — |

`deploy-vercel.yml` scatta su `apps/web/**`: un runner npm deployerebbe a ogni
test. È un limite d'impianto **accettato**, non un buco da chiudere. Va scritto
qui una volta per non riaprirlo ogni ciclo.

---

## Cosa sta fuori da tutti e tre i perimetri — misurato, non elencato

Il 07/09 ho passato in rassegna ogni area che i tre cicli potevano aver lasciato
fuori, misurandola prima di metterla in lista. **Sei aree su nove non sono un
punto**, e va scritto perché non le riapra nessuno:

| Area | Misura del 07/09 | Esito |
|---|---|---|
| Route API Next.js | 170 su 170 passano da uno dei tre helper di proxy/auth | non è un punto |
| Edge Functions | deployate il 27/08 (v40, v13); il repo è avanti di un commit del 29/08, **10 righe, tutte commenti** | allineate; il deploy resta manuale (`supabase functions deploy`), rischio già in memoria |
| Backup | procedura di ripristino provata il 10/8 (`docs/BACKUP_DISASTER_RECOVERY.md`) | non è un punto |
| `worker/run.py` | 56% di copertura, nella media del backend | non è un punto |
| Job schedulati a DB | `pg_cron` non installato: nessun job nascosto | non è un punto |
| Drift DB ↔ repo | 78 corpi di funzione live su 78 confrontati col repo (md5 a spazi normalizzati): 0 differenze sostanziali, 3 cosmetiche (accenti, `=`/`:=`) | non è un punto |
| **Logica SQL dentro il DB** | 78 funzioni (cifra del 07/09; sul live oggi sono **75**), 26 trigger, 96 policy: allora mai contate né eseguite da un test → **20 eseguite dall'08/09**, vedi la riga aggiornata sopra | **Punto 1** |
| ~~Registro delle correzioni~~ | ~~4.132 righe, 0 attori~~ → **chiuso 08/09**: le scritture su `fatture` dichiarano l'attore | ✅ |
| Script che scrivono a DB | 41 veri, 8 vivi dopo il go-live, 18 fuori dal repo | **Punto 3**, ridimensionato |

---

## Cosa si controlla, in ordine

> **Un punto per volta, chiuso davvero** (WORKFLOW.md §5). L'ordine è per
> danno potenziale, non per dimensione.

### Punto 1 — I numeri che il cliente vede li calcola anche il database, e nessuno l'ha mai letto

I tre cicli hanno contato `.py` e `.ts` (il contatore 09: `find services utils
config worker -name "*.py"` più le Edge Functions). Dentro `supabase/migrations/`
ci sono **8.930 righe di SQL**, e una parte non è schema: è **logica che gira in
produzione a ogni scrittura**.

| Misura (07/09, repo e DB live) | Valore |
|---|---:|
| Funzioni SQL definite | 78 (2.048 righe di corpo) |
| di cui **calcolano numeri o spostano fatture** | **32 funzioni, 1.028 righe** |
| Trigger attivi sul DB live | 26 |
| Policy RLS | 96 |
| Punti del codice che le chiamano con `.rpc()` | 32 |
| Test che ne **eseguono** una riga | era **0**; dal 07/09 sono **38** (`tests/test_sql_*.py`), su un Postgres locale vero |

L'audit Database di luglio (30/7) ha guardato **schema, FK, orfani, indici** —
9 finding — non i corpi delle funzioni. Il contatore di settembre non li ha mai
contati. Questa è l'unica logica di produzione che **nessun metro ha mai toccato**.

**Da dove si parte** (le funzioni che scrivono o calcolano soldi, per righe):
`sposta_fattura_a_sede` (88), `dashboard_stats_aggregata` (88),
`riparto_quote_mensili` (85), `assegna_fattura_a_sede` e la variante tecnica
(57+66), `sync_margini_mensili_from_ricavi` (60), `scadenziario_fatture_aggregate`
(55), `crea_riparto_con_quote` e `sostituisci_quote_riparto` (38+38),
`costi_automatici_mensili` e la variante gruppo (26+28), `claim_batch_for_processing`
(31), `soft_delete_fatture_massivo` con `fn_propagate_deleted_at_fatture`.

#### Verbale della lettura — 07/09/2026, fase Fable

**Letti 78 corpi su 78** (76 nomi: `get_distinct_files` esiste in tre versioni),
presi dal DB live con `pg_get_functiondef`, non dai file. Le 26 funzioni che
aggiornano solo `updated_at` o bumpano una cache sono lette e scartate in blocco.

| Cosa ha detto la lettura | Misura |
|---|---|
| Formule MOL, netto, primo margine in SQL vs Python | identiche (`riparto_quote_mensili` ↔ `services/routers/margini.py`; `costi_automatici_mensili` ↔ letture del worker) |
| Colonne snapshot di `margini_mensili` (`mol`, `primo_margine`, `*_perc`) | scritte da tre scrittori, **lette da nessuno**: ogni lettura ricalcola. Il dubbio della prima stesura (il trigger dei ricavi non ricalcola il MOL) è innocuo |
| Funzioni `SECURITY DEFINER` eseguibili con la chiave **anon** | **2**: `gruppo_tag_analisi` (ricreata con `DROP` il 27/08, i `REVOKE` del 19-20/06 sono saltati: restituisce la spesa di qualsiasi sede a chi indovina una descrizione) e `get_next_ordine_ricetta` (innocua) |
| RPC che PostgREST non sa risolvere | `get_distinct_files` chiamata col solo `p_user_id` → `PGRST203 Could not choose the best candidate` (provato il 07/09 con la chiave vera). Oggi ci passa solo `elimina_tutte_fatture` senza sede, che logga e va avanti con un conteggio parziale |
| Funzioni senza nessun chiamante nel codice | 5: `gruppo_prezzi_categoria`, `swap_ricette_order`, `create_ristorante_for_user`, `conta_ristoranti_utente`, `get_distinct_files(text)` |
| Liste di categorie F&B ricopiate in SQL | 3 copie (`_riparto_categoria_is_fb`, `gruppo_spreco_fb_categorie`, esclusioni di `gruppo_peso_categoria`): oggi uguali a `config/constants.py`, nessun test le confronta |
| `data_competenza` vs `data_documento` | dashboard, chat e spreco aggregano per data documento; margini e gruppo per competenza. Divergono su 229 righe, 3.794 €, 1 sede |
| Limite giornaliero della chat | `chat_usage_check_and_log` azzera a mezzanotte **UTC** (01:00/02:00 italiane) |
| Sede tecnica «Costi comuni» (P.IVA copiata dalla prima sede reale) | 49 fatture SDI in coda su quella sede: 44 assegnate a mano dal cliente, 5 precedenti al tracciamento; **0 smistate automaticamente** — senza indirizzo non vince mai |

**Il fatto che decide il presidio: il repo non sa ricostruire il database.**
Applicando tutte le 230 migration (91 legacy + 139 canoniche) a un Postgres
vuoto: **18 tabelle su 59, 28 funzioni su 78, 171 file falliscono**. `fatture`,
`users`, `app_settings` e `memoria_ai_categorie` non hanno un `CREATE TABLE` in
nessun file; le altre esistono ma in ordine che non si applica. E
`20260730234500_turni_tipo_giorno.sql` contiene un apostrofo non escapato
(`indennita')`) che è un errore di sintassi: il DB live ha quel commento, quindi
è stata applicata a mano, non come file. «Un Postgres in CI con le migration
applicate» non è un'opzione: non c'è niente da applicare.

**Decisione (07/09).** Il presidio si costruisce su uno **snapshot dello schema
live** (`supabase/schema_snapshot.sql`: tabelle, vincoli, indici, funzioni,
trigger, grant — generato dai cataloghi, non da `pg_dump`, che non c'è) più le
migration canoniche **successive** allo snapshot, caricati in un Postgres locale
a ogni run (`pgserver`, wheel pip da 11 MB con Postgres 16 embedded; il live è
17.6). Niente servizio in CI, niente accesso al DB di produzione dai test. I
test seminano righe e chiamano le funzioni. **Il criterio non cambia**: si
altera un corpo nello snapshot o in una migration successiva, un test diventa
rosso. Lo snapshot si rigenera quando si applica una migration; il confronto
snapshot ↔ live resta uno script a lancio manuale.

**Lavoro della fase Opus.** Punti 1 e 2 chiusi il 07/09; 3, 4 e 5 aperti.

- ✅ **1. Snapshot + fixture.** `supabase/schema_snapshot.sql` (3.940 righe)
  riproduce il live verificato oggetto per oggetto: 59 tabelle, 78 funzioni, 26
  trigger, 216 vincoli, le stesse 6 funzioni aperte ad `anon`. Caricato in un
  Postgres locale effimero (`pgserver`, in `requirements-lock.txt`); la fixture
  applica sopra le migration più recenti dello snapshot. La guardia di rete del
  conftest lascia passare i soli socket UNIX: il DB dei clienti è su TCP+TLS e
  resta irraggiungibile. Primo test: le liste di categorie F&B ricopiate in tre
  funzioni SQL, 34 casi, provati per mutazione.
- ✅ **2. Sicurezza: 6 funzioni erano raggiungibili dalla chiave pubblica**, non
  2. La più grave è `gruppo_tag_analisi` (SECURITY DEFINER): dato l'id di una
  sede e una descrizione, restituiva spesa e fornitori senza verificare il
  chiamante. **Chiuso in produzione il 07/09 alle 15:2x**, con permesso esplicito
  di Mattia fuori dalla finestra oraria perché il buco era aperto.
  Verificato sul live dopo l'applicazione: `anon` 0 funzioni (erano 6),
  `authenticated` 0, `service_role` 6 su 6 e 13 RPC su 13 intatte. E dall'esterno
  con la chiave pubblica vera via `/rest/v1/rpc/`: `HTTP 401 permission denied`.
  I quattro advisor Supabase su quelle funzioni sono spariti.
  > ⚠️ **La causa non è il DROP+CREATE**, come credevo. Sono le *default
  > privileges* del progetto (`pg_default_acl`): concedono EXECUTE ad `anon` e
  > `authenticated` su **ogni** funzione creata, con grant **nominali**. Un
  > `REVOKE … FROM PUBLIC` da solo non li toglie — la prima stesura della
  > migration non chiudeva nulla, e sembrava corretta. Trovato dal
  > `code-reviewer` **eseguendola**, non leggendola. Ne segue che ogni funzione
  > futura nasce aperta: il presidio è `tests/test_sql_funzioni_permessi.py`.
- ⬜ **3.** Migration che elimina le 5 funzioni morte (chiude anche il `PGRST203`).
- ⬜ **4.** Test per mutazione sulle sei che muovono soldi o fatture:
  `costi_automatici_mensili`, `riparto_quote_mensili`,
  `sync_margini_mensili_from_ricavi`, `scadenziario_fatture_aggregate`,
  `sposta_fattura_a_sede`, `claim_batch_for_processing`.
- ⬜ **5.** Le due divergenze minori (competenza; fuso del limite chat) restano
  qui finché Mattia non decide se sono difetti.

**Il limite che resta aperto.** Lo snapshot va in drift appena si applica una
migration al live. `scripts/genera_schema_snapshot.py --check` lo rileverebbe,
ma richiede `SUPABASE_DB_URL` (connessione diretta al Postgres) che il progetto
non ha: oggi lo snapshot è stato prodotto via MCP. Metterlo in CI vorrebbe dire
dare alla CI una connessione al DB dei clienti — peggio del problema. Per ora il
drift si nota perché la fixture applica le migration nuove sopra lo snapshot e
fallisce rumorosamente se non si applicano.

### Punto 2 — Il registro delle correzioni — fatto e spedito l'08/09/2026

> **Review del cumulativo (08/09, ore 11:00, sui tre commit `2e21b3a`, `6a73b73`,
> `e3f59ff`): 🔴 NON CHIUSA** su due residui — nessuno in produzione, entrambi
> veri. **BL-1**: rimettendo `.execute()` al posto di `fetch_all` in
> `categoria_batch` (`services/routers/fatture.py`, due select) la suite intera
> resta verde: il fix del troncamento a 1000 righe non ha rete. **BL-2**: lo
> snapshot era stato riallineato a mano, e `fn_log_category_change` non coincide
> col live. La prima review (ore 07:01) era sul solo primo commit; i fix delle
> 07:29 non erano stati ri-revisionati. Entrambi i residui stanno nella Parte A
> di `docs/piani/PROMPT_FUNZIONI_SQL_VIVE.md`. Il registro ha **0 righe dal
> deploy** (ultima scrittura 03/09 14:53): chiuso sul codice, **non ancora
> confermato dai dati** — la prima riga con `source='worker_coda'` sarà la prova.

**Era**: `category_change_log` doveva dire chi ha cambiato una categoria, e non lo
sapeva — 4.132 righe, 0 attori su ogni colonna, un solo `source` distinto. Il
trigger cercava i dati nel JWT (auth custom: mai presente) e in GUC che nessuno
impostava.

**Ora**: le scritture di `categoria` su `fatture` dichiarano chi sono. Dettaglio,
misure e residuo in [«Cosa ha chiuso il Punto 2»](#cosa-ha-chiuso-il-punto-2-0809).

Commit: `2e21b3a` (impianto), `6a73b73` (blocchi della review), `e3f59ff`
(migration al live + snapshot). Spediti, CI verde, worker in produzione.

### Punto 3 — Gli script che scrivono in produzione, ridimensionati dalla misura

La prima stesura contava 49 script scrittori e 0 test. Rimisurato con un criterio
più stretto (crea un client Supabase **e** chiama `update/insert/upsert/delete`):

| Misura (07/09) | Valore |
|---|---:|
| Script che scrivono davvero a DB | **41** (non 49: `dict.update` e `list.insert` gonfiavano il conto) |
| di cui **fuori dal repo** | **18**: tutta `tools/` (ignorata da git, `.gitignore:20`) + 7 `debug_*`/`verifica_*` |
| di cui vivi dopo il go-live (toccati da agosto) | **8**, tutti con `--dry-run` di default |
| di cui monouso di aprile-giugno, 1 commit, ancora eseguibili | **15** |
| Test che ne coprono uno | 3 file, di cui `tests/test_ricategorizza_sede_pipeline.py` è una **replica** del codice, non lo script |

L'asimmetria dry-run della prima stesura resta vera ma è piccola: un solo script
tracciato scrive senza flag (`scripts/backfill_totali_fatture.py`, aprile, monouso
che richiede una cartella di XML); l'altro è in `tools/`, quindi fuori dal repo.

**Il lavoro**, in quest'ordine: (a) gli **8 vivi** si leggono per la classe di
bug del 26/08 — *può sovrascrivere una correzione manuale?* — e per ciascuno si
scrive un test che esegua lo script, non una replica; (b) i **15 monouso** si
cancellano: codice che nessuno esegue ma che può ancora scrivere sui dati veri;
(c) la convenzione dry-run diventa una sola riga in CLAUDE.md. I 18 fuori dal
repo non sono lavoro di audit: sono una decisione di Mattia (dentro o via).

> **Il Punto 2 ha cambiato la forma di questo lavoro (aggiunto l'08/09).**
> Ri-misurato oggi: **41 script scrittori** (30 in `scripts/`, 11 in `tools/`),
> di cui **6 scrivono `categoria`** e quindi passano dal trigger del registro:
>
> | Script | Ultimo commit | Nota |
> |---|---|---|
> | `scripts/ricategorizza_sede.py` | 26/08 | è lo script del precedente del 26/08 |
> | `scripts/ricategorizza_sede_ai.py` | 26/08 | stesso giorno, stessa classe |
> | `scripts/catscan_applica.py` | 05/06 | applica correzioni da un JSON |
> | `tools/fix_sospette_memoria_globale.py` | non tracciato | **scrive cross-tenant senza filtro `user_id`**: la scrittura più larga del repo |
> | `tools/fix_stale_cache.py` | non tracciato | per-utente |
> | `tools/check_cache_prodotti.py` | non tracciato | id e liste hardcoded |
>
> Per questi sei il lavoro non è più solo «testarli»: è **farli dichiarare**, con
> `source='script_manuale'` e un `batch_id` per esecuzione, usando il chokepoint
> `aggiorna_categoria_fatture` che ora esiste. Oggi ogni loro riga finisce nel
> registro come `db_trigger` anonima — cioè indistinguibile dal worker.
> `scripts/_recalc_review_sushiland.py` risulta nei grep ma scrive solo
> `needs_review`, non `categoria`: **è un falso positivo**, non contarlo.

---

## Un difetto trovato archiviando, non cercandolo — chiuso il 07/09

**`_DOC_STATO` in `scripts/claude_hook_reviewer_gate.py` era codice morto.**
Il confronto cercava il documento di stato in `file_toccati`, da cui i `.md`
sono esclusi a monte (e questo file è comunque ignorato da git): l'avviso
«nessun aggiornamento a stato/contatore» usciva **sempre**, anche a documento
aggiornato. Ora il gate misura l'ultima modifica su disco di questo file
rispetto all'avvio della sessione. Tre test in
`tests/test_hook_reviewer_gate_sessione.py`, provati per mutazione: confronto
invertito, file assente trattato come aggiornato, avviso mai emesso — tutti e
tre uccisi.

---

## Cosa NON si fa in questo ciclo, e perché

- **Non si rifanno le 10 dimensioni di luglio.** Ferme dal 29/7-4/8 su ~103.000
  righe (oggi 114.808), ma il ciclo di settembre ha riletto quel codice con la
  lente della copertura. Rifarle è costo senza copertura nuova.
- **Non si insegue la copertura backend oltre il 61%.** Le aree grasse sono state
  prese: negli ultimi dieci giorni ogni file aperto ha dato un bug vero (una sede
  a 0,00 € invece di 402.168; 4,4 M€ di scadenze invisibili; i tag su metà
  prodotti; il food cost sbagliato di 2-4 punti). Il rendimento ora cala.
- **Non si costruisce un runner npm** per le 42.293 righe di `.tsx`. Settimane di
  lavoro per coprire rendering, e riprogettare il deploy.
- **Non si tocca il costo del personale fermo a luglio.** Il MOL di agosto e
  settembre non è confrontabile, ma il briefing avvisa già i clienti dal 28/08 e
  sono loro a inserirlo (Margini → «Costo personale»). **Decisione di Mattia del
  07/09: lo inseriranno i clienti, non è lavoro nostro.** Non riaprirlo.
- **Non si riaprono i router uno per uno.** 10 su 12 restano a copertura parziale:
  è vero, ed è il metro sbagliato. Si coprono quando si toccano.
- **Non si leggono le 96 policy RLS una per una.** Con `auth.uid()` sempre NULL e
  ogni client su `service_role`, non filtrano niente: la protezione è
  applicativa, ed è già la dimensione Security di luglio.

---

## Come si chiude questo ciclo

Quando i punti 1, 2 e 3 sono chiusi con presidio provato **per mutazione**.
Allora questo file si sposta in `docs/storico/` e **non se ne apre un altro**:
da lì in poi vale la regola ordinaria — *quando tocchi un file, lo copri*.

> **La lezione che questo ciclo eredita, e che vale più delle cifre:** ogni ciclo
> ha misurato ciò che sapeva misurare e ha chiamato «100%» il proprio perimetro.
> Il buco non era dentro nessuno dei tre — era **fra** i tre. E la prima stesura
> di questo file lo ha rifatto in piccolo: ha scelto due script prima di misurare.
> Prima di dichiarare finita un'area, chiedersi *cosa è rimasto fuori dalla
> domanda che ho fatto*.
