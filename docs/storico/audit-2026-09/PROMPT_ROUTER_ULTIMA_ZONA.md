# Prompt sessione — chiudere l'audit: i router del worker

> **Modello**: **Opus**, `ultrathink` in apertura — i router muovono i soldi dei
> clienti (margini, riparto, ricavi) e toccano la regola di dominio #1.
> **Sforzo**: alto. È una dimensione di audit, non un fix.
> **Voce di roadmap**: §0 #4 di `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-09.md`.
> **Stato repo alla stesura**: `c48249a`, coda push **0**, suite **13.010 verdi**.

---

## ⚠️ Prima di tutto: NON fidarti di questo file

Ogni cifra qui è misurata il **06/09/2026, ore 06:00**. In questo progetto le
premesse dei prompt sono state smentite dalla misura **in 5 casi su 10**, e
sull'area `agenda/` la verità è cambiata **tre volte in tre documenti**.

**Ri-misura prima di crederci**, e misura **la proprietà che decide** (gli
importi, non i record): «ci sono 107 righe» e «quelle righe muovono denaro» sono
due misure diverse, e la prima non implica la seconda.

```bash
find services utils config worker -name "*.py" | xargs wc -l | tail -1
{ git ls-files apps/web/src; git ls-files --others --exclude-standard apps/web/src; } \
  | grep -v -E '\.(woff|woff2|svg|png|jpg|ico)$' | xargs wc -l | tail -1
find services/routers -name "*.py" | xargs wc -l | sort -rn
```

⚠️ **Nel frontend serve anche `--others`**: con `git ls-files` da solo un file
nuovo non ancora tracciato sparisce dal conto e il totale esce più basso del
vero. Già successo il 05/09.

---

## Dove siamo

| Perimetro | Righe | Copertura |
|---|---:|---|
| Backend | 56.989 | **100%** — zona rossa chiusa |
| Frontend | 53.955 | 94% — **3.316 mai guardate** |
| Edge Functions | 3.556 | **100%** |
| **App** | **114.500** | **97%** |

**Ma il 97% non è il numero che conta.** Delle righe «coperte», solo **~51% sono
state lette riga per riga**: il resto è passato sotto una lente specifica
(Security, Bug, AI…), che trova i difetti *di quella classe* e tace sulle altre.
Il ciclo 07 lo ha già dimostrato: la prima passata su `ai_service.py` lasciò
~3.900 righe non lette, e il secondo giro trovò lì l'HIGH più grave.

---

## La misura che conta: copertura reale per router

`routers/` = **16.915 righe** (ri-misurate il 07/09), di cui **15.538 ancora parziali**, l'unico blocco grande a copertura parziale. Il
perimetro **sicurezza** è chiuso (216 endpoint su 216 protetti, ri-verificato il
03/09); la **logica** no.

⚠️ **Il prompt precedente classificava i router per "quante volte i test li
nominano"** — una misura che ammetteva lei stessa di non misurare niente. Questa
tabella conta invece, per ogni router, **quanti dei suoi endpoint compaiono in un
test**, e le affianca il denaro che ci passa. Misurata il 06/09:

| Router | Righe | Endpoint | Testati | Copertura | Denaro / dati a DB |
|---|---:|---:|---:|---:|---|
| `prezzi.py` | 1.385 | 10 | 1 | **10%** | `prezzi_preferiti`: **8 righe** — quasi vuota |
| `cestino.py` | 252 | 5 | 1 | **20%** | soft delete su 39.466 righe fattura |
| `tag.py` | 394 | 14 | 3 | **21%** | `custom_tag_prodotti` 170 · **regola #1** |
| `gruppo.py` | 2.385 | 8 | 2 | **25%** | catena multi-sede |
| `scadenziario.py` | 587 | 11 | 3 | **27%** | avvisi scadenze |
| `admin.py` | 3.200 | 48 | 15 | **31%** | **solo staff**, non clienti |
| ~~`margini.py`~~ | 1.377 | 12 | 12 | ✅ **fatto il 06/09** | il MOL — 8 mutanti, 7 uccisi. **Non rilavorarlo** |
| `workspace.py` | 2.494 | 52 | 22 | **42%** | turni/personale — toccato il 05-06/09 |
| `account.py` | 557 | 8 | 4 | **50%** | |
| `fatture.py` | 1.367 | 15 | 4 | **27%** | **4,05 M€** su 11 sedi — ⚠️ era dichiarato 8/15: ri-contando i path nei test sono **4** |
| `ricavi.py` | 1.506 | 8 | 7 | **87%** | **14,77 M€** incassi, 6 sedi |
| `riparto.py` | 1.402 | 12 | 12 | **100%** | letto e misurato sano il 04/09 (Q4) |

**Anche questa non è copertura vera**: dice che l'endpoint è *nominato* in un
test, non che il test provi il comportamento. È un filtro per scegliere da dove
partire, e va **rifatta**, non ereditata.

### Cosa dice la misura, contro le priorità del vecchio prompt

- **`ricavi.py` non è più una priorità**: era indicato come area da attaccare, è
  all'**87%**. Ha però l'importo più grande dell'app (14,77 M€): se lo tocchi,
  verifica che quei presidi provino il comportamento e non solo la formula.
- **`prezzi.py` è il meno presidiato (10%) ma la sua tabella ha 8 righe.** È lo
  stesso caso di `agenda/`: misura prima, o lavori su un'area che muove 0 €.
- **Il candidato è `fatture.py`**: volume (4,05 M€, 39.466 righe, alimentate di
  recente) e copertura reale **27%**, non 53% — la cifra del 06/09 era
  sovrastimata. `margini.py`, l'altro candidato di allora, **è stato chiuso il
  06/09**: lì il difetto c'era davvero (una sede a 0,00 € invece di 402.168).
- **`admin.py` è il più grande e mal coperto, ma serve solo lo staff**: un
  difetto lì non raggiunge un cliente. Ultima priorità, non prima.

**Non affrontarli in blocco**: un router per volta, chiuso davvero (WORKFLOW.md §5).

---

## Il residuo frontend (3.316 righe) — dopo i router

Nessuna di queste aree muove denaro (misurato). La colonna chiude a scarto 0.

| Area | Righe | Perché è rossa |
|---|---:|---|
| `(auth)` + `(legal)` + `(demo)` | 1.353 | nessun dato economico |
| `(app)/agenda/` | 692 | 107 turni, `costo_orario` **NULL su 107/107** → **0 €** |
| `app/` file radice | 481 | include `globals.css` (296) |
| `(app)/assistenza/` | 292 | `marketplace_leads` **0 righe** |
| `(app)/style-guide/` | 256 | pagina interna |
| `proxy.ts` + `hooks/` | 127 | |
| `(app)/layout+loading` | 115 | guscio |

---

## Cosa NON rifare

Chiuse con presidio provato per mutazione — rifarle è costo senza copertura:

- **Prompt AI** (`config/`), **briefing**, **worker/** — sessione Fable, 03-04/09
- **`utils/`** e i **19 moduli `services/`** — 05/09
- **`margini/`, `catena/`, `scadenziario/`, `dashboard/`, `notifiche/`,
  `impostazioni/`** frontend — cicli 08-09
- **Q1, Q2, Q4** chiusi il 04/09; **Q3** il 05/09; **R1-R11** tutti chiusi
- **Turni / ore extra** — 05-06/09, vedi sotto

---

## Il lavoro del 05-06/09 (contesto, non da rifare)

**Modello ore extra invertito**: erano additive (09-17 con 2 extra = 10 ore), ora
sono un **sottoinsieme** (8 ore, di cui 2 di straordinario).

**Il fix parziale ha lasciato indietro dei consumatori tre volte.** Prima export
Excel e `/m`; poi l'aggregazione del tab Personale desktop (8 ore con 10 extra →
**10 ore e 100 €** invece di 8 e 80, +25% nella card dei totali); infine l'export
backend, che pagava le extra su un turno senza tariffa mentre il frontend
mostrava 0 — **lo stesso turno con due importi diversi**.

Ora la regola vive in **una sola fonte**, `apps/web/src/lib/ore-turno.ts`
(`ripartisciOre`, `aggregaPerPersona`, `costoTurnoGiornaliero`), importata da
desktop e mobile. Lato Python restano 4 punti (`_ore_turno` nel worker,
`margini.py`, `workspace.py`, `personale_export_service.py`): **cercali col grep,
non fidarti di questa lista** — è già stata incompleta tre volte.

**La causa a monte è chiusa**: un valore impossibile è rifiutato con un 400 su
**tutti e 4** gli endpoint di scrittura (POST e PATCH, giornaliero e mensile).
Prima validavano solo le due POST, e la guardia si aggirava creando una riga
valida e modificandola subito dopo. 16 test in
`tests/test_turni_ore_extra_validazione.py`.

**18 mutanti, 18 uccisi**, dopo che **4 sono sopravvissuti alla prima stesura**.
Nessuno indicava codice ridondante: ognuno indicava un test che non provava
quello che dichiarava.

### ⚠️ Quattro trappole, se tocchi guardie o presidi simili

1. **Il PATCH è parziale**: i totali vanno letti dalla riga a DB *e* il body deve
   avere la precedenza, o la guardia rende il campo **immodificabile**. Due
   mutanti rompevano il caso legittimo, non quello illegittimo.
2. **Un assert su un aggregato non vede gli errori che si compensano**: il test
   `oreStd + oreExt == 8.0` passava col bug, perché `-2 + 10` fa 8. Asserisci le
   **componenti**.
3. **Due parametri vanno incrociati**: un test con extra eccedenti (tariffa
   unica) e uno con tariffa maggiorata (extra in-range) lasciavano vivo il
   mutante — con una sola tariffa gli errori si annullano.
4. **Il turno 22:00-02:00 vale 4 ore, non −20** (`timedelta.seconds`): una
   guardia ingenua rifiuterebbe ogni turno serale, il caso normale di un
   ristorante.

**Esposizione a DB: zero** (107 turni; `ore_extra` valorizzato su 92 ma **tutti a
0**; `costo_orario` NULL su 107/107; ultimo inserimento 05/09 08:20).
**Ri-misuralo**: un cliente può aver inserito turni nel frattempo.

---

## Decisioni aperte di Mattia (non lavoro tecnico)

1. **`mol_perc`** — colonna morta misurata (1 scrittore, **0 lettori**, 75 righe
   di cui 18 non-zero). Droppare o lasciare come storico inerte. 1 riga di SQL.
2. **`costo_orario` nel dialog giornaliero** — di fatto facoltativo. Non
   rimuoverlo finché il costo non arriva dal cedolino: oggi è **l'unica fonte**
   del costo personale nel MOL.
3. **Esclusività giornaliero/mensile** — **decisa il 05/09: NON si tocca.** È la
   guardia contro il doppio conteggio del personale nel MOL.

**Non è una decisione di Mattia**, ed è un errore già fatto: il **costo del
personale ago+set** (7 sedi su 7 a zero) lo inseriscono **i clienti**, e il
briefing li avvisa già. Nessuna azione tecnica.

---

## Il metodo che regge (WORKFLOW.md §5)

1. **Misura prima di scegliere l'area**: conta le righe a DB e guarda **gli
   importi**, non i record. `prezzi.py` è il router meno coperto e ha 8 righe.
2. **Un presidio si prova per mutazione**, o non è un presidio. Un mutante per
   volta, backup `.bak` preso **prima del primo**, md5 verificati al ripristino.
   Un mutante sopravvissuto va **dichiarato**: nelle ultime 18 prove, 4 su 4
   indicavano un test debole, **nessuno** codice ridondante. Il modo di deciderlo
   è **eseguire le due versioni affiancate** su casi limite, non ragionarci.
3. **`tsc` e un test verde non provano niente.** Esegui il codice — il TypeScript
   vero con `node --experimental-strip-types`; per testare la logica di un `.tsx`
   estraila prima in `lib/`, l'unico posto che `tests/helpers_ts.py` sa eseguire.
   E il presidio deve coprire **il punto d'uso**, non solo la funzione estratta:
   un mutante nel chiamante è sopravvissuto a 1.100 test verdi.
4. **Cerca le inerenze**: chi altro chiama la funzione toccata? Copie duplicate,
   `/m` (frontend separato, da allineare a mano), export, edge functions, RPC SQL.
   **Cambiare il comportamento in un punto crea una divergenza nei punti che non
   cambi**: la scelta su cosa fare di un dato mancante va portata a *tutti* i
   percorsi che lo leggono, nello stesso commit.
5. **`/code-reviewer` prima di chiudere** — è un gate, non un optional. Il
   05-06/09 sono servite **4 passate**: ogni giro ha trovato qualcosa che il giro
   precedente aveva corretto solo dove si vedeva.
6. **Non modificare i sorgenti mentre la suite gira**:
   `test_route_api_auth_dichiarativa` usa `inspect.getsource` e fallisce leggendo
   un file a metà. Un rosso finto costa un'ora di indagine.
7. **Ri-somma la colonna, non aggiungere il tuo delta**, e verifica **gli
   addendi**, non solo il totale: due errori opposti fanno quadrare la somma. Il
   05/09 il totale chiudeva a scarto 0 con un addendo nella colonna sbagliata.

---

## Definizione di «finito» per questa sessione

Non «il 100% di copertura» — è un obiettivo che si raggiunge solo dichiarando
coperto ciò che non lo è. Finito significa:

- **una dimensione chiusa davvero**: presidio per mutazione, commit, verbale,
  contatore ri-misurato addendo per addendo, `check_documentazione.py` pulito;
- il contatore che **chiude a scarto 0** dopo il tuo lavoro;
- ciò che resta scoperto **dichiarato con la sua ragione**, non nascosto in una
  percentuale.
