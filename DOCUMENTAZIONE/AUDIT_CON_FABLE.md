# Audit con Fable — storico delle sessioni

> **A cosa serve questo file.** È lo storico, voluto da Mattia, delle sessioni
> di audit fatte con Claude Fable: una sezione datata per sessione, scritta per
> essere riletta fra mesi. Il dettaglio tecnico sta nei verbali del ciclo
> (`AUDIT_ONEFLUX_STATO_2026-09_STORICO.md`) e nei report in `scratchpad/`;
> qui c'è il racconto di cosa è stato fatto e cosa ha cambiato per i clienti.

---

## Sessione 03–04/09/2026 — «Tutte le voci del piano, una dopo l'altra»

**Mandato di Mattia**: partire dalla prima voce della roadmap di audit (§3
dello stato ciclo 2026-09) e percorrerle TUTTE, in ordine, fino in fondo.
**Esito**: 6 voci su 6 percorse in una sola sessione — 5 chiuse, la sesta
avviata a programma com'era previsto. 14 commit locali (`0f29285` → `80fd929`),
ogni chiusura con verbale, presidio provato per mutazione e contatore di
copertura ri-misurato. A fine sessione: **12.908 test verdi su 12.908**,
code-review indipendente sul cumulativo e sul delta, entrambe verdi.

### 1. Quadratura dei numeri fra le pagine ✅

La prima verifica mai fatta sui dati veri dei clienti: lo stesso numero deve
tornare identico in ogni schermata dove compare. **I conti tornano al
centesimo** (riparto in partita doppia 18/18, Analisi Fatture ↔ Margini,
sincronia ricavi). Emersi 4 esiti (Q1–Q4, registrati in §2 dello stato):
un bug al segnale «margine in calo» della catena, due decisioni di prodotto
che spettano a Mattia (definizione del food cost; righe non classificate nel
riparto) e una rete da mettere sullo storico dei margini.

### 2. I prompt AI (`config/`) ✅

Il cuore della categorizzazione, mai guardato prima. La struttura regge:
29 categorie coerenti fra prompt, costanti e database, zero categorie
estranee in produzione, e la contraddizione interna del prompt è neutralizzata
dal codice per disegno. Trovate e riparate **12 voci del dizionario
illeggibili** (corrotte da una doppia codifica: non potevano riconoscere
nessun prodotto), con una rete che impedisce il ritorno del problema.

### 3. Categorizzazione — le 5 fasi rimaste del piano ✅

Il piano da 10 fasi è ora completo:
- **Fase 4** — le righe classificate-ma-dubbie possono uscire dai margini,
  ma dietro un interruttore SPENTO: si accende solo col via di Mattia, dopo
  aver applicato la migration e ri-misurato il delta per sede (oggi: zero).
  Scoperta di misura: le funzioni DB da toccare erano 7, non le 19 del piano.
- **Fase 4bis** — la Home ha la card «Righe da classificare»: dice quante
  righe e quanti euro restano fuori dai margini, verde solo quando è vero.
- **Fase 5** — ogni correzione manuale del cliente ora insegna al sistema, su
  tutti e tre i percorsi; e **319 correzioni già fatte dai clienti**, che
  l'automatismo poteva sovrascrivere per una svista di etichetta, sono ora
  protette.
- **Fase 6** — la memoria globale non si fida più della sola parola dell'AI:
  378 voci mai viste da un umano sono state declassate a suggerimento.
- **Fase 8** — il correttore di refusi non scambia più le parole corte
  (una polo da 60 € era finita in CARNE per colpa di POLLO→POLO).

### 4. Il briefing giornaliero ✅

Letto riga per riga per la prima volta: **l'impianto regge** — i numeri sono
calcolati dal codice, l'AI riscrive solo il tono, e la validazione introdotta
il 2/9 in produzione tiene (zero violazioni negli snapshot reali). Due
credenze di ciclo sono risultate invecchiate alla ri-misura (le soglie del
documento di briefing oggi combaciano tutte col codice). Chiusi due difetti
latenti: importi delle scadenze scritti all'inglese e il validatore che non
copriva l'entusiasmo vietato.

### 5. Il worker asincrono ✅

La roadmap lo dava per «non presidiato»: misurato, era il contrario — è tra i
moduli più difesi dell'app, e le code sono in salute (647 fatture elaborate,
zero arretrati). Chiuso un difetto latente: il meccanismo di ri-tentativo
della coda ricavi-email non avrebbe mai potuto scrivere la sua schedulazione.

### 6. I router — prima passata (a programma) 🟠

La voce va per router, non in blocco. La prima passata ha chiuso la scoperta
più importante della sessione: **gli avvisi sulle scadenze erano muti da
giugno** — ogni tentativo di generarli falliva in silenzio, e nessun cliente
ha mai ricevuto un avviso a fronte di 300 fatture scadute per 4,4 milioni di
euro visibili nello scadenziario. Riparato e provato: dal prossimo deploy
campanella e briefing ricominciano ad avvisare.

### Cosa resta, e di chi è

- **Il push** (37 commit in coda, 14 di questa sessione): ordine di Mattia,
  finestra serale. La CI non ha ancora visto nulla di tutto questo.
- **Al deploy**: applicare la migration della Fase 4; l'interruttore si
  accende solo dopo, con delta ri-misurato.
- **Decisioni di Mattia già registrate**: Q2 e Q4 (quadratura), i 153
  conflitti fra memoria del cliente e memoria globale, le righe storiche da
  ricategorizzare.
- **Fix pronto per una sessione dedicata**: Q1, il segnale «margine in calo»
  (prompt già scritto in `docs/piani/PROMPT_Q1_SEGNALE_MARGINE_CALO.md`).
- **Le passate successive dei router**, in ordine di rischio cliente.

### Il metodo che ha retto anche stavolta

Ogni cifra ereditata è stata ri-misurata prima di crederci, e la lista dei
casi in cui il documento aveva torto si è allungata: «19 RPC» erano 7,
«worker non presidiato» era il contrario, «6 soglie sbagliate» erano state
già sistemate, «357 voci» erano confermate ma per la ragione giusta solo dopo
il riconteggio. E ogni presidio nuovo è stato provato rompendolo apposta
(mutazione), non dichiarato.
