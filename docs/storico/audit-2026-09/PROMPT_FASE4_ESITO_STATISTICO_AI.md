# Prompt per la sessione — Fase 4: l'esito statistico dell'AI

> **ESEGUITO e CHIUSO il 14/09/2026.** Questo file e' archiviato: si legge
> come storia di cosa era stato previsto, non come lavoro da fare. La misura
> ha rovesciato la domanda della lente — l'AI decide l'1,3% delle righe, non
> abbastanza perche' "quanto sbaglia l'AI" sia la domanda giusta. Esito reale
> nel verbale del 14/09 in `AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`.

> **Come si usa.** Imposta il modello secondo la tabella qui sotto (§ «Modello e
> sforzo»), apri una sessione nuova e incolla la sezione «PROMPT». Tutto il
> resto del file è contesto che la sessione leggerà da sola: non serve
> incollarlo.

---

## PROMPT (copia da qui)

Apri la **Fase 4 della sessione trasversale di audit: L4 — esito statistico
dell'AI**. È la quarta delle nove lenti trasversali; L1, L3 e L2 sono chiuse il
14/09/2026.

Leggi prima, in quest'ordine:
1. `DOCUMENTAZIONE/AUDIT_COPERTURA.md` → sezione «Lenti trasversali» (cosa è
   chiuso, con quale metro, e la riga L4 fra quelle da fare)
2. `WORKFLOW.md` §6 → come si conduce un audit **e la regola sul costo**
3. `docs/piani/PROMPT_FASE4_ESITO_STATISTICO_AI.md` → perimetro, metodo,
   criteri di chiusura e le trappole già pagate su questa materia

**Il problema in una riga:** la categorizzazione AI è il cuore del prodotto — è
ciò per cui il cliente paga — e **nessuno sa quanto spesso sbaglia, né dove**.
Esistono prove che il singolo pezzo funziona (prompt, guardrail, dizionario,
memoria), ma non esiste **una misura dell'esito**: quante righe escono giuste,
quante sbagliate, **per quale fonte di decisione**, e su quali categorie il
sistema si confonde sistematicamente. Finora l'unica cifra è una **misura cieca
su 815 righe del 1/9 — 96,7% corrette** — che non distingue le fonti e non è
più stata rifatta da quando la Fase 6 ha cambiato le regole del bypass.

**Nota di realtà sulla riga della tabella.** `AUDIT_COPERTURA.md` descrive L4
come «tasso di correzione per fonte, matrice di confusione, golden set dalle 319
correzioni manuali». La parte «per fonte» **va misurata prima di crederci**: il
log di audit `category_change_log` aveva 4.135 righe con **0 attori** e `source`
a un solo valore (`db_trigger`), e su quel campo un tasso «per fonte» sarebbe
rumore. Il campo che regge davvero è `fatture.categoria_fonte` (Fase 2 del piano
categorizzazione, 01/09): **verifica quante righe l'hanno popolato oggi** —
al 1/9 erano **0 su 39.224** perché il codice non era ancora in produzione. Se
sono ancora poche, la lente cambia forma: si misura sul ground truth umano e si
dichiara che la stratificazione per fonte non era disponibile.

**Vincolo di costo, non negoziabile.** Rilevatori, script e misure si fanno **in
sessione**: niente workflow multi-agente. L'unico sub-agente è il
`code-reviewer` a fine fase. Il motivo sta in `WORKFLOW.md` §6: nella sessione
del 13-14/09 il fan-out ha bruciato 2,5M token producendo triage, non prove.
La velocità non è il vincolo; il budget dell'abbonamento sì.

⚠️ **Questa lente spende soldi veri**: ogni riga ri-classificata è una chiamata
OpenAI. Prima di lanciare qualunque batch, **stima il costo e dichiaralo a
Mattia**, e taratura su un campione piccolo prima del resto.

**Non pushare.** Si lavora su `main` locale; il push è una decisione serale di
Mattia. Misura tu la coda all'apertura e dichiarala (il 14/09 erano 8 commit).

Apri con `/apertura-sessione`, poi dichiara il perimetro che hai **misurato tu**
(non quello che leggi qui: le sessioni parallele committano) e parti.

## (fine prompt)

---

## Modello e sforzo

`AUDIT_COPERTURA.md` raccomanda **Fable normale**. La raccomandazione regge, con
una precisazione che viene dall'esperienza di L2:

| Parte della fase | Modello | Sforzo |
|---|---|---|
| Apertura, scelta del metro, decisione su cosa è ground truth | **Opus** | `ultrathink` |
| Esecuzione: script di misura, batch, tabelle, matrice di confusione | **Fable** | normale |
| Eventuali fix al codice di classificazione | **Opus** | `ultrathink` (è una regola di dominio: CLAUDE.md §1) |

**Perché `ultrathink` solo in apertura.** Il rischio di questa lente non è
l'esecuzione — contare è meccanico — è **scegliere male cosa conta come
"giusto"**. Un golden set costruito sulle correzioni manuali misura *dove i
clienti hanno guardato*, non *dove il sistema sbaglia*: le categorie che nessuno
controlla non compaiono negli errori proprio perché nessuno le ha corrette. Quel
ragionamento va fatto con lo sforzo alto, prima di scrivere il primo script.

**Perché non `ultracode`/workflow.** Vale `WORKFLOW.md` §6 e il vincolo di costo
qui sopra: il fan-out su lavoro di misura non aggiunge qualità. La domanda da
porsi è «cosa mi dà un agente che una query non mi dà?» — qui la risposta è
niente: i dati stanno in due tabelle e il giudizio è uno solo.

---

## Contesto della fase — misurato il 14/09/2026 (RI-MISURARE, non ereditare)

Le letture al DB di produzione sono state **negate dal classificatore di auto
mode** in questa sessione: le cifre qui sotto vengono dal codice e dai documenti,
non dal database vivo. **Sono tutte da rifare all'apertura** — ed è la ragione
per cui la prima cosa che fa la sessione è misurare.

| Cosa | Dove si misura | Ultima cifra nota |
|---|---|---|
| Righe fattura attive | `fatture` con `deleted_at IS NULL` | 39.224 (01/09) |
| Righe con provenienza | `fatture.categoria_fonte IS NOT NULL` | **0 su 39.224** (01/09) — da rifare |
| Ground truth umano | `prodotti_utente` con `classificato_da LIKE 'Manuale (%@%'` **+** la grafia legacy `'User'` | **319** (03/09) |
| Log modifiche categoria | `category_change_log` | 4.135 righe, **0 con attore**, `source` monovalore (11/09) |
| Memoria globale | `prodotti_master` | 2.913 voci, 1.671 verificate (04/09) |
| Misura cieca precedente | citata in `PIANO_CATEGORIZZAZIONE.md` — **la baseline `scratchpad/risultati_giudizio.json` NON esiste piu'** (verificato il 14/09) | 815 righe, **96,7% corrette** (01/09), non riproducibile |

**Il motore da misurare** è `services/ai_service.py` (5.865 righe). I livelli di
decisione sono già nominati nel commento della migration
`20260901170000_fatture_provenienza_categoria.sql`, e sono il vocabolario della
matrice: `L0_fornitore`, `L1_admin`, `L1_5_non_negoziabile`, `L2_locale`,
`L3_globale`, `L3_globale_non_verificata`, `L4_dicitura`, `L5_fornitore`,
`L6_um`, `L7_dizionario`, `L7_regola_forte`, `AI_alta`, `AI_confermata`,
`nessuna`. `NULL` = legacy.

## Cosa esiste già — non riscriverlo

Quattro script coprono pezzi di questa misura. **Leggili prima di scrivere il
tuo**: rifarli da zero è il modo tipico di spendere mezza sessione.

| Script | Cosa fa già |
|---|---|
| `scripts/ab_test_modello_categorizzazione.py` | ground truth dalle correzioni manuali (con la grafia legacy `User`), A/B fra due modelli, costo reale |
| `scripts/_confronta_modelli_ai.py` | AI **pura** (nessuna regola/dizionario a valle) su 607 prodotti, accuratezza + costo per modello |
| `scripts/audit_processo_classificazione.py` | statistiche aggregate su `prodotti_utente` |
| `scripts/audit_fase6_rientro_bypass.py` | distribuzione dello streak, declassate vs controllo; distingue «via chiusa» da «nessun traffico» |

## Metodo proposto

1. **Misura a DB prima di scegliere il taglio** (`/apertura-sessione` §3): quante
   righe hanno `categoria_fonte`, come si distribuiscono per fonte e per
   fiducia, quante correzioni manuali esistono oggi e su quali categorie.
   Se la provenienza è ancora vuota, **dillo subito**: cambia la lente.
2. **Decidi cosa è "giusto", e scrivi perché.** Le correzioni manuali sono un
   campione **distorto dall'attenzione del cliente**; un campione casuale
   giudicato a mano è più onesto ma costa tempo. Qualunque scelta va dichiarata
   col suo bias, non presentata come verità.
3. **Matrice di confusione** categoria attesa × categoria assegnata, e la stessa
   **stratificata per fonte** se la provenienza lo consente. Quello che si cerca
   non è il tasso medio: sono le **celle dense** — le coppie che il sistema
   confonde sempre nello stesso verso.
4. **Tasso di correzione per fonte**: quante righe di ogni livello un umano ha
   poi cambiato. È la misura che dice quale livello **non merita la fiducia che
   ha**, e va letta sapendo la base (una fonte con 12 righe non ha un tasso).
5. **Golden set permanente** dai casi confermati, come test, così una regressione
   del prompt o del dizionario si vede. ⚠️ Un golden set che **rilegge** la
   risposta del modello non è un presidio se il modello non viene chiamato:
   il test deve essere deterministico o marcato, non una chiamata OpenAI in CI.
6. **Fix dei difetti confermati**, ognuno con mutante sul **call site**
   (`WORKFLOW.md` §6): mutare la funzione non prova che qualcuno la usi.

## Criteri di chiusura (WORKFLOW §5 — «una cosa alla volta, chiusa davvero»)

- [ ] La misura esiste ed è **riproducibile**: uno script versionato, non un
      numero incollato in un documento
- [ ] Ogni cifra dichiarata è stata misurata **col comando che la frase dichiara**
      (la lezione ricorrente del ciclo: 3 cifre sbagliate su 3 avevano un comando
      dietro, ma non quello che la frase diceva)
- [ ] Il bias del campione è scritto accanto al risultato, non omesso
- [ ] Ogni fix ha il suo mutante ucciso, mutato sul call site
- [ ] Il golden set è un presidio provato per mutazione, non una chiamata a OpenAI
- [ ] `python -m pytest tests/ -q` e `python -m pytest -q -m sql` verdi
- [ ] `python scripts/check_documentazione.py` pulito
- [ ] Verbale (≤ 40 righe) in
      `docs/storico/audit-2026-09/AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`
- [ ] Riga **L4** nella tabella «Lenti trasversali» di
      `DOCUMENTAZIONE/AUDIT_COPERTURA.md`, con metro, artefatto e «si riapre se…»,
      e L4 rimossa da «Le lenti ancora da fare» con **L5 promossa a prossima**
- [ ] `code-reviewer` sul cumulativo `origin/main..main` — **un solo agente**
- [ ] Commit su `main` locale. **Nessun push.**

## Trappole note su questa fase

- **Una percentuale senza la sua base non è una misura.** «Il livello X sbaglia
  il 40%» su 5 righe non dice niente: la base va scritta accanto alla
  percentuale, sempre.
- **Il ground truth delle correzioni manuali è cieco dove nessuno guarda.** Le
  categorie che il cliente non controlla non producono correzioni, quindi
  sembrano perfette. Dirlo nel verbale.
- **`category_change_log` non ha attori**: `source` ha un solo valore e i GUC che
  il trigger legge non li imposta nessun codice applicativo (misurato l'11/09 su
  4.135 righe). Un filtro «senza attore umano» selezionerebbe il 100% delle
  righe. Chiuso come Punto 2 dell'audit dell'08/09 con la RPC
  `aggiorna_categoria_fatture_attribuita`: **verifica quante righe nuove hanno un
  attore da allora** prima di usare o scartare quel campo.
- **Ogni riga ri-classificata costa.** Stima prima, campiona prima, e dichiara la
  spesa a Mattia — non è una misura gratuita come le altre lenti.
- **Un mock generoso resta verde sul bug.** Se il golden set gira su un client
  finto che risponde a tutto, non misura il motore: vale la lezione di
  `tests/helpers_supabase_sql.py` scritto per L2.
- **`Da Classificare` non è un errore.** È lo stato esplicito e onesto
  (CLAUDE.md §1): va contato a parte, mai come sbaglio del modello. Il margine
  vero, secondo la misura cieca del 1/9, **è lì** e non negli errori.
- **La misura del 96,7% non è riproducibile**: il suo file di baseline non esiste
  più nello scratchpad. Va rifatta, non citata — ed è il primo motivo per cui
  questa lente produce uno **script versionato** invece di un numero.

## Dopo la Fase 4

Restano L5-L9, ognuna una sessione a sé, in ordine e col modello consigliato
nella tabella «Le lenti ancora da fare» di `DOCUMENTAZIONE/AUDIT_COPERTURA.md`.

## Residui che questa fase eredita (non suoi, da non raccogliere per inerzia)

- **Snapshot dello schema da rigenerare**: `supabase/schema_snapshot.sql` ha
  perso `GENERATED BY DEFAULT AS IDENTITY` su `gruppo_tags` /
  `gruppo_tag_prodotti`, oggi rattoppato dentro la fixture di
  `tests/test_isolamento_per_risorsa.py` (debito dichiarato da L2).
- **NUOVO 1 del piano categorizzazione**: il guardrail IVA scarta la risposta
  giusta (`docs/piani/PIANO_CATEGORIZZAZIONE.md`). È vicino a questa materia ma
  **non** è questa lente: se la misura lo conferma, si annota, non si apre.
