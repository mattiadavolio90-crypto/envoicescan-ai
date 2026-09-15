# Prompt per la sessione — Fase 5: ciclo di vita di colonne e campi

> **Come si usa.** Imposta **Fable, sforzo normale** (è inventario meccanico:
> vedi §«Modello e sforzo»), apri una sessione nuova e incolla la sezione
> «PROMPT». Il resto del file è contesto che la sessione leggerà da sola.

---

## PROMPT (copia da qui)

Apri la **Fase 5 della sessione trasversale di audit: L5 — ciclo di vita di
colonne e campi**. È la quinta delle nove lenti trasversali; L1, L3, L2 e L4 sono
chiuse il 14/09/2026.

Leggi prima, in quest'ordine:
1. `DOCUMENTAZIONE/AUDIT_COPERTURA.md` → sezione «Lenti trasversali»
2. `WORKFLOW.md` §6 → come si conduce un audit **e la regola sul costo**
3. `docs/piani/PROMPT_FASE5_CICLO_DI_VITA_CAMPI.md` → perimetro **già misurato**,
   il rilevatore **già provato**, e le trappole già pagate

**Il problema in una riga:** il DB ha **667 colonne su 59 tabelle**, cresciute in
sei mesi di sviluppo veloce, e nessuno sa quali siano ancora vive. Una colonna
scritta e mai letta è lavoro sprecato a ogni riga inserita; una **letta e mai
scritta** è peggio, perché qualcuno sta leggendo un valore che non arriva mai —
ed è la classe di difetto che in questo progetto ha già prodotto KPI a zero e
gate che tagliavano mesi di dati.

**Il lavoro di scoperta è già fatto: parti da qui, non da zero.** Misurato il
15/09/2026 (ri-misura, non ereditare): **20 colonne candidate morte su 336 nomi
distinti**, trovate in **6 secondi**. Il rilevatore prototipo è in
`docs/piani/_L5_rilevatore_colonne.py`. Due di quelle 20 sono già **confermate
morte** dalla lente L4 (`correzioni_count`, `ultimo_correttore`): usale come
taratura — se il tuo rilevatore non le trova, è rotto lui.

**Vincolo di costo, non negoziabile.** Rilevatori e misure si fanno **in
sessione**: niente workflow multi-agente. L'unico sub-agente è il
`code-reviewer` a fine fase (`WORKFLOW.md` §6).

**Non cancellare niente.** Questa lente produce **un inventario e una proposta**,
non una migration: far cadere una colonna è distruttivo e irreversibile, e la
decisione è di Mattia. Se trovi una colonna **letta e mai scritta** quello sì è
un difetto da correggere subito, con mutante sul call site.

**Non pushare.** Si lavora su `main` locale; misura tu la coda all'apertura e
dichiarala (il 15/09 erano 11 commit).

Apri con `/apertura-sessione`, dichiara il perimetro che hai **misurato tu**, e
parti.

## (fine prompt)

---

## Modello e sforzo

`AUDIT_COPERTURA.md` raccomanda **Sonnet/Fable normale**, e la raccomandazione
regge: contare occorrenze è meccanico. Con una precisazione:

| Parte della fase | Modello | Sforzo |
|---|---|---|
| Inventario: rilevatore, conteggi, triage delle 20 | **Fable** | normale |
| Giudizio su una colonna dubbia (viva? morta? letta e mai scritta?) | **Fable** | normale |
| Fix di una colonna **letta e mai scritta** | **Opus** | `ultrathink` se tocca margini/categorie (regola di dominio) |

**Perché non serve `ultrathink` in apertura**, a differenza di L4: lì il rischio
era scegliere male il metro, qui il metro è ovvio (la colonna compare o no). Il
rischio è diverso — **credere al grep** — e si governa con le trappole qui sotto,
non con più ragionamento.

---

## Perimetro — misurato il 15/09/2026 (RI-MISURARE, non ereditare)

| Cosa | Misura |
|---|---|
| Tabelle `BASE TABLE` in `public` | **59** (il doc diceva «60») |
| Colonne totali | **667** |
| Nomi di colonna distinti | **336** |
| File di codice scansionati | 540 (`services utils config worker scripts apps/web/src`) |
| Tempo di una passata completa | **6,1 secondi** |
| Candidate morte al primo giro | **20** |

Le tabelle più larghe: `fatture` 36 colonne (39.646 righe), `users` 35 (8),
`margini_mensili` 31 (75), `fatture_documenti` 27 (3.905), `ristoranti` 24 (15),
`fatture_queue` 24 (677).

## Le 20 candidate del primo giro

```
ack ack_at ack_by confirmed_at confirmed_by correlation_id correzioni_count
data_elaborazione dismissed_notification_ids fornitore_norm idempotency_key
ignored_at ignored_by ignored_until is_correct note_admin note_pagamento
oggetto_hash ultimo_correttore validato_da
```

**Almeno una di queste è viva** (`idempotency_key`, vedi trappola 1): la lista è
un punto di partenza, non un verdetto. Il lavoro della fase è classificarle una
per una e **cercare la classe opposta**, che il primo giro non trova.

## Il rilevatore: com'è fatto e perché così

`docs/piani/_L5_rilevatore_colonne.py` — **una sola lettura dei file, tutte le
colonne contate insieme**:

```bash
find services utils config worker scripts apps/web/src \
     -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) > /tmp/files.txt
python docs/piani/_L5_rilevatore_colonne.py /tmp/files.txt <colonna> <colonna> ...
```

**Perché non un grep per colonna:** ci mette ~7 secondi *per colonna* (oltre
un'ora per 336), e `grep -r` su `apps/web/` scende dentro `node_modules` — il
primo tentativo è andato in **timeout a 120 secondi**. `rg` non è installato.

**Taratura obbligatoria prima di credergli** (valori del 15/09):

| Colonna | Attesa | Riscontri |
|---|---|---|
| `correzioni_count` | morta (L4) | 0 |
| `ultimo_correttore` | morta (L4) | 0 |
| `consecutive_correct_classifications` | viva | 4 |
| `categoria_fonte` | viva | 12 |
| `tipo_attivita` | viva | 16 |
| `deleted_at` | viva | 37 |

## Trappole già pagate su questa fase — non ripagarle

1. **Il grep su Python/TS non vede l'SQL.** `idempotency_key` ha 0 riscontri nel
   codice applicativo ed è **viva**: è un `unique (...)` in migration. Il secondo
   giro va fatto su `supabase/` (migration + Edge Function).
2. **Creazione ≠ uso.** Tutte e 20 compaiono in `supabase/`, ma quasi sempre è
   solo la riga che le crea. Discriminante **provata**: escludendo `add column`,
   la riga di definizione e i commenti, `correzioni_count` e `correlation_id`
   restano a **zero** (morte davvero), mentre `idempotency_key` e `oggetto_hash`
   conservano un uso reale.
3. **Nomi corti senza word boundary.** `ack` matcha dentro «fallback». Il regex
   con `\b` non è un dettaglio.
4. **Una colonna può essere scritta da un trigger, una view o un default**, senza
   comparire mai nel codice. Prima di dire «morta»: `pg_trigger`, le view, e
   `column_default` in `information_schema`.
5. **Il frontend può leggere per nome dinamico** (`row[campo]`): un grep sul nome
   non lo vede. Vale per le colonne servite dalle API in blocco.
6. **«0 righe a DB» non è «colonna morta»**: può essere nuova. E il contrario —
   una colonna piena di dati può non essere letta da nessuno.

## La classe che il primo giro NON trova, ed è la più grave

Il rilevatore conta le **occorrenze**, quindi trova le colonne che il codice non
nomina. Non trova quelle che il codice **legge** ma **nessuno scrive**: lì le
occorrenze ci sono. Vanno cercate separatamente — per ogni colonna, distinguere
le occorrenze in *lettura* (`select`, accesso al dizionario) da quelle in
*scrittura* (`insert`, `update`, `upsert`) — e confrontate con i dati: una
colonna letta dal codice e **NULL al 100%** sul DB è la firma di quella classe.

Precedenti nel progetto, tutti di questa famiglia: il KPI a `0,00 €` che leggeva
lo snapshot mentre l'altro tab leggeva l'override; il costo del personale assente
sui mesi recenti che tagliava gli ultimi due mesi a ogni gate; il radar verde su
`fatture_documenti.upload_id`, **colonna mai esistita**.

## Criteri di chiusura (WORKFLOW §5)

- [ ] Ogni colonna delle 20 (più quelle trovate dopo) ha un esito classificato:
      viva / morta / **letta e mai scritta** / scritta da trigger o view
- [ ] La classe «letta e mai scritta» è stata cercata **esplicitamente**, non
      solo dedotta dall'assenza di occorrenze
- [ ] Ogni difetto vero corretto con mutante sul **call site**
- [ ] L'inventario è un artefatto versionato e **riproducibile** (uno script, non
      una lista incollata), con la sua taratura sui casi noti
- [ ] Nessuna colonna cancellata: la proposta di drop è una lista per Mattia
- [ ] `python -m pytest tests/ -q` e `python -m pytest -q -m sql` verdi
- [ ] `python scripts/check_documentazione.py` pulito
- [ ] Verbale (≤ 40 righe) in
      `docs/storico/audit-2026-09/AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`
- [ ] Riga **L5** in «Lenti trasversali» di `DOCUMENTAZIONE/AUDIT_COPERTURA.md`,
      con metro e «si riapre se…», L5 tolta da «ancora da fare» e **L6 promossa**
- [ ] `code-reviewer` sul cumulativo `origin/main..main` — **un solo agente**
- [ ] Commit su `main` locale. **Nessun push.**

## Residui che questa fase eredita

- **Le due colonne morte di L4**: `prodotti_master.correzioni_count` e
  `ultimo_correttore` (0 scrittori, 0 lettori) — già confermate, da mettere
  nell'inventario.
- **Snapshot dello schema da rigenerare**: `supabase/schema_snapshot.sql` ha
  perso `GENERATED BY DEFAULT AS IDENTITY` su `gruppo_tags` /
  `gruppo_tag_prodotti`, oggi rattoppato nella fixture di
  `tests/test_isolamento_per_risorsa.py` (debito dichiarato da L2). **Questa
  lente tocca lo schema: è l'occasione naturale per saldarlo.**

## Dopo la Fase 5

Restano L6-L9, in ordine, col modello consigliato nella tabella «Le lenti ancora
da fare» di `DOCUMENTAZIONE/AUDIT_COPERTURA.md`.
