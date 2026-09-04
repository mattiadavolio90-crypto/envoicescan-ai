# Copertura audit — il contatore

> **A cosa serve.** È l'unico posto dove si risponde a «quanta dell'app è stata
> davvero controllata». I cicli chiudono dimensioni, ma nessun altro documento
> somma le righe: senza questo file si sa *cosa* è stato chiuso, non *quanto*
> manca. **È anche l'unico posto dove le somme devono tornare.**

**Ri-misurato il 4/09/2026.** Le cifre si ri-misurano a ogni aggiornamento, mai
ereditate da qui — nemmeno dalla riga sopra:

```bash
find services utils config worker -name "*.py" | xargs wc -l | tail -1
git ls-files apps/web/src | grep -v -E '\.(woff|woff2|svg|png|jpg|ico)$' | xargs wc -l | tail -1
find supabase/functions -name "*.ts" | xargs wc -l | tail -1
```

> ⚠️ **La misura invecchia mentre la scrivi.** Il backend è passato da 56.699 a
> 56.787 righe nell'ora in cui questo file veniva riscritto: un'altra sessione
> stava committando. Le sessioni parallele sono il regime normale — la cifra vale
> per il momento in cui è presa, e va ripresa, non ricopiata.

---

## Tre stati, e cosa significano

- **📖 Letto integralmente** — qualcuno ha letto il file riga per riga e lo ha
  dichiarato. È la copertura forte.
- **🔍 Auditato per dimensione** — il modulo è passato sotto una lente specifica
  (Security, Bug, AI, Performance…). Trova i difetti *di quella classe*, non dice
  nulla sulle altre. Il ciclo 07 lo dimostra: la prima passata su `ai_service.py`
  lasciò ~3.900 righe non lette, e il secondo giro trovò lì l'HIGH più grave.
- **🔴 Mai guardato** — non compare in nessuna passata.

**«Area chiusa» significa: la logica pura è coperta e provata per mutazione**, non
«ogni riga ha un test». In `margini/` le 4.711 righe sono state lette tutte, ma i
test ne raggiungono ~400: il resto è JSX, hook, stato e recharts, che l'harness
non sa montare. È un limite dichiarato, non una svista.

---

## Il totale

| Perimetro | Righe |
|---|---:|
| Backend Python (`services/`, `utils/`, `config/`, `worker/`) | 57.393 |
| Frontend (`apps/web/src/`, esclusi i binari) | 53.764 |
| Edge Functions (`supabase/functions/`) | 3.556 |
| **TOTALE APP** | **114.713** |

> Ri-misurato il **4/09/2026 sera** coi comandi qui sopra (dopo il deploy di
> `a5e77f1`). Il backend è cresciuto di 479 righe e il frontend di 525 rispetto
> al 3/09: sono il lavoro della **sessione Fable**
> ([`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md)), la chiusura di Q1 e le altre
> sessioni in parallelo. **La misura invecchia: ri-prendila, non ricopiarla.**

### Quanta app è coperta — la risposta in una riga

| Perimetro | Coperto (📖 + 🔍/🟠) | Mai guardato 🔴 | % coperta |
|---|---:|---:|---:|
| Backend | 48.048 | 9.345 | **84%** |
| Frontend | 27.210 letti su 53.764 | ~26.554 | **51%** |
| Edge Functions | 3.556 | 0 | **100%** |
| **App intera** | **78.814** | **35.899** | **69%** |

> **Come si legge.** «Coperto» somma il letto integralmente (📖) e il parziale
> (🔍/🟠): sono livelli di confidenza diversi, non equivalenti — il dettaglio per
> modulo sta nelle tabelle sotto. La riga Frontend è la più debole: la
> ripartizione per area è ferma al 3/09 e va ri-misurata area per area (vedi
> l'avviso in quella sezione). Le Edge Functions risultano coperte al 100% dai
> cicli precedenti, con 101 test Deno.

---

## Backend Python — 57.393 righe

| Modulo | Righe | Stato | Riferimento |
|---|---:|---|---|
| `db_service.py` | 2.284 | 📖 letto | ciclo 07, 8/8 |
| `invoice_service.py` | 2.333 | 📖 letto | ciclo 07, 10/8 |
| `auth_service.py` | 1.782 | 📖 letto | ciclo 07, 8/8 |
| `ai_service.py` | 5.744 | 📖 nucleo decisione + gate | ciclo 09: motore unico, gate, 9 uscite. 101 test. **4/09 fasi 5-6-8** ([`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §3): apprendimento sui 3 percorsi, bypass memoria globale, refusi parole corte |
| `upload_handler.py` | 2.282 | 🔍 chiamante del gate | passa descrizione e fornitore a `valuta_fiducia` |
| `margine_service.py` | 1.487 | 🔍 di rimbalzo | **regola di dominio MOL**; 3/9 il filtro «Da Classificare» viene dalla costante (R6); 4/09 allineato al flag Fase 4 ([`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §3) |
| `fastapi_worker.py` | 8.899 | 🔍 per router | voce Salute coperta con 10 test dopo il bug del 2/9; 3/9 le 4 copie del filtro «Da Classificare» legate alla costante (R6) |
| `daily_briefing_service.py` | 1.660 | 📖 letto | **4/09, sessione Fable** ([`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §4): letto riga per riga, impianto confermato; chiusi 2 difetti latenti (importi all'inglese, validatore entusiasmo) |
| `routers/` (tutti) | 16.755 | 🟠 parziale | ~4.000 letti nel ciclo 07; **216 endpoint su 216 protetti** e guardia a livello di router (R5) — perimetro *sicurezza* chiuso, *logica* no. **4/09, sessione Fable** ([`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §6, prima passata): `scadenziario` — gli avvisi erano **muti da giugno**. 4/09 **Q1**: `gruppo.py` segnale «margine in calo» |
| `worker/` | 2.411 | 📖 letto | **4/09, sessione Fable** ([`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §5): «gira non presidiato» era **falso** — 7 file di test worker, code in salute (647 fatture, 0 arretrati). Chiuso il retry della coda ricavi-email |
| `utils/` | 2.574 | 🔴 | — |
| `config/` | 2.411 | 📖 letto | **contiene i prompt AI** — la regola di dominio n.1. **3/09, sessione Fable** ([`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md) §2): 29 categorie coerenti, 1.268 chiavi validate, 12 mojibake riparate con presidio |
| `services/` (altri moduli) | 6.771 | 🔴 | riparto, foodcost, price_impact, radar… |

**Backend: copertura dopo il 4/09.** Ri-sommata la colonna (non per delta):

| Stato | Righe | % | Moduli |
|---|---:|---:|---|
| 📖 letto integralmente | 18.625 | 32% | `db_service` 2.284, `invoice_service` 2.333, `auth_service` 1.782, `ai_service` 5.744, `daily_briefing_service` 1.660, `worker/` 2.411, `config/` 2.411 |
| 🔍 / 🟠 parziale | 29.423 | 51% | `fastapi_worker` 8.899, `routers/` 16.755, `upload_handler` 2.282, `margine_service` 1.487 |
| 🔴 mai guardato | 9.345 | 16% | `utils/` 2.574, `services/` altri moduli 6.771 |
| **Totale backend** | **57.393** | 100% | ✅ la colonna chiude (verificata addendo per addendo) |

> Le tre cifre sono state **ri-sommate voce per voce**, non stimate: la prima
> stesura dava 20.078 / 27.963 / 9.275, che sommavano a 57.316 solo perché il
> totale era stato fatto quadrare a mano. Ri-misurando i moduli uno per uno
> (`services/` altri moduli sono **6.771**) i tre numeri veri sono questi. È
> esattamente l'errore contro cui questo file mette in guardia in fondo: *un
> delta non è una somma*. **Ri-misurate il 4/09 sera**: ogni addendo con `wc -l`,
> e la somma confrontata col totale — delta **0**.

**Le due zone rosse rimaste** sono `utils/` e gli altri moduli di `services/`
(riparto, foodcost, price_impact, radar…). Sono l'unica parte del backend che
nessuna passata ha ancora guardato: è lì che va la prossima dimensione, non sulle
voci già coperte da Fable.

---

## Cosa ha coperto la sessione Fable (03-04/09)

> Lavoro **autonomo, aperto e chiuso**, raccontato in
> [`AUDIT_CON_FABLE.md`](AUDIT_CON_FABLE.md). Non fa parte del ciclo di audit del
> progetto e non ci si riporta dentro. Compare **qui** perché questo file ha un
> solo compito — dire quanta app è controllata davvero — e ignorare 5 voci
> coperte lo renderebbe falso.

| Voce roadmap §3 | Perimetro | Esito | Da ripassare? |
|---|---|---|---|
| #2 prompt AI | `config/` (2.411) | 12 chiavi mojibake riparate, presidio per mutazione | **No** |
| #3 categorizzazione | `ai_service`, `routers/` | 10 fasi su 10, test per fase | **Sì, con Opus** — regola di dominio #1, flag ancora spento (migration `20260903210000` già applicata: 7 RPC su 7, verificata il 04/09) |
| #4 briefing | `daily_briefing_service` (1.660) | letto riga per riga, 2 difetti chiusi | **No** |
| #5 worker | `worker/` (2.411) | «non presidiato» smentito: 7 file di test | **No** |
| #6 router | `routers/` (16.755) | prima passata: scadenziario muto da giugno | **Sì, con Opus** — 1 router su molti |

**Effetto sul contatore, quantificato:** `config/` (2.411) e `worker/` (2.411)
passano da 🔴 a 📖 — **4.822 righe** che risultavano mai guardate — e
`daily_briefing_service.py` (1.660) da 🔍 a 📖. Senza contare Fable, il backend
coperto scenderebbe da 84% a **72%** (41.566 su 57.393) e le zone rosse
salirebbero da 9.345 a 14.167 righe. **È già incluso in tutte le cifre di questo file**: escluderlo
darebbe una copertura più bassa del vero.

**Cosa resta da ripassare con Opus** (non da rifare da zero): **#3
categorizzazione** — tocca la regola di dominio #1 e ha un flag ancora spento
(la migration è già applicata) — e **#6 router**, dove la prima passata ha coperto
un solo router su molti. Le altre tre voci sono chiuse con presidio provato per
mutazione: rifarle è costo senza copertura nuova.

---

## Frontend — 53.764 righe

> ⚠️ **Ri-misurato il 4/09: 53.764 righe (+525 dal 3/09).** La tabella qui sotto
> è ferma alla ripartizione per area del 3/09 e **non è stata ri-sommata**: le
> 525 righe nuove (sessione Fable + sessioni in parallelo) non sono attribuite a
> nessuna area. Dichiarato invece che ricalcolato a mano, perché ri-sommare 20
> aree senza ri-misurarle una per una produrrebbe l'errore che questo file ha già
> pagato tre volte. **Da ri-misurare area per area alla prossima passata frontend.**

> **Le somme di questa tabella chiudono a 53.233**, ri-sommate contro
> `git ls-files` il 3/9 sera (20 aree). Restano **6 righe** non coperte da
> nessuna riga di area: erano 60, e sono scese ri-misurando le 5 aree toccate
> da R10 invece di lasciarne crescere il delta. Le tre stesure precedenti non chiudevano: giravano tre
> totali diversi (51.413, 51.614, 52.998) nello stesso file, perché ogni sessione
> aggiungeva il proprio delta invece di ri-sommare la colonna. **Ri-somma sempre,
> non sommare delta.**

| Area | Lette | Totali | Stato | Riferimento |
|---|---:|---:|---|---|
| `app/api/` — 170 route | 4.871 | 4.871 | 📖 | ciclo 09, 30/8 — proxy trasparente, 0 route toccano il DB |
| `(app)/margini/` | 4.711 | 4.711 | 📖 | ciclo 09, 31/8 — 183 test, 65/65 mutanti. Resta il rendering |
| `(app)/scadenziario/` | 2.238 | 2.238 | 📖 | ciclo 09, 31/8 (15/15 mutanti) + 3/9 (R10: il guasto non è più un vuoto). Resta il rendering |
| `(app)/catena/` | 2.977 | 2.977 | 📖 100% | ciclo 09, 1/9 (3 passate) + 3/9 (R3, `pct`, `fatture/`). 326 test. `card-segnali.tsx` (110) è **esclusione motivata**, non un buco: fetch + JSX. `fatture/page.tsx` letta il 3/9: nessun difetto proprio, ma ci è stato trovato **R10** (pattern su ~8 pagine, non di catena). Resta il rendering |
| `(app)/analisi-e-tag/` | 1.420 | 1.546 | 📖 92% | ciclo 07 §3c; 3/9 lo stato vuoto non invita più a rifare i tag che esistono (R10) |
| `lib/` | 2.433 | 5.581 | 🟠 44% | i moduli estratti dalle sessioni di settembre; `format.ts` è la fonte unica del parsing; `esito-caricamento.ts` (3/9) distingue il guasto dal vuoto numerico (58 chiamanti) |
| `(app)/admin/` | 1.739 | 3.871 | 🟠 45% | ciclo 07 §3c — solo staff, non clienti |
| `(app)/prezzi/` | 973 | 2.358 | 🟠 41% | ciclo 07 §3c |
| `(app)/workspace/` | 1.834 | 5.021 | 🟠 37% | ciclo 07 §3c + F6 ciclo 08: il resto escluso con misura |
| `(mobile)/` | 1.283 | 4.008 | 🟠 32% | ciclo 07 §3c; 3/9 avvisi mobile allineati al desktop (R10) |
| `(app)/analisi-fatture/` | 825 | 2.677 | 🟠 31% | ciclo 07 §3c; 3/9 il tab Articoli non dice più «nessun prodotto» su un worker giù (R10) |
| `components/` | 2.188 | 7.299 | 🟠 30% | F3 ciclo 08: 2.188 lette, 2.414 campionate, 2.675 escluse con misura |
| `(app)/dashboard/` | 0 | 1.685 | 🟠 logica estratta | 1/9: la logica è uscita nei moduli `home-*.ts`, 92 test. Nessun `.tsx` letto |
| `(app)/impostazioni/` | 0 | 808 | 🟠 logica estratta | 2/9: logica in `piani.ts` + `impostazioni-account.ts`, 22 test |
| `(app)/notifiche/` | 23 | 265 | 🟠 logica estratta | 2/9: logica in `notifiche-shared.ts`, 23 test; 3/9 le due pagine avvisi non mentono più (R10) |
| `(app)/agenda/` | 0 | 693 | 🔴 | **0 turni a DB**: scartata con misura, non dimenticata |
| `(app)/assistenza/` | 0 | 292 | 🔴 | `marketplace_leads` 0 righe |
| `(app)/style-guide/` | 0 | 256 | 🔴 | pagina interna |
| `(auth)` + `(legal)` + `(demo)` | 0 | 1.353 | 🔴 | 552 + 575 + 226 |
| `hooks/` + file diretti + proxy | 0 | 723 | 🔴 | include `globals.css` |

**Somma: lette 27.210 · non lette 25.772 · totale 52.982** (ri-sommata il
3/09/2026, non aggiornata per delta).

> ⚠️ **La tabella chiude a 52.982, il repo misura 53.031: mancano 49 righe.**
> Vengono da aree cresciute senza che la loro riga fosse ri-misurata, non dal
> lavoro del 3/09 (+5 righe nette). Dichiarato invece che nascosto in un
> arrotondamento — chi ri-misura un'area, chiuda anche questo.
>
> ⚠️ **Si misura con `git ls-files`, non con `*.tsx`.** La riga di `catena/`
> diceva 2.938 perché il glob `cat catena/*.tsx` **non entra nelle
> sottocartelle**: si è perso `catena/fatture/page.tsx` (77 righe, mai lette).
> Un glob che non scende è un modo silenzioso di misurare meno app di quella che
> c'è — trovato dal code-reviewer il 3/09.

Le righe non lette dentro un'area 🟠 **non sono terra vergine**: una passata ha
delimitato il perimetro e motivato l'esclusione (di solito: esposizione live
bassa). Rileggerle da zero è il lavoro fantasma che il metodo vieta.

---

## Edge Functions — 3.556 righe

📖 **Copertura completa e verificata** (13/13 file, 2 passate, ciclo 07).
È l'unico perimetro dove «completo» è stato controllato file per file.

---

## Il conto onesto

| | Righe | % | da dove viene |
|---|---:|---:|---|
| 📖 Letto integralmente | 37.435 | **33%** | 6.364 backend + 27.515 frontend + 3.556 Edge |
| 🔍 / 🟠 Auditato o parzialmente coperto | 58.885 | 52% | 36.369 backend + 22.516 frontend |
| 🔴 Mai guardato | 17.256 | **15%** | 14.054 backend + 3.202 frontend |
| **Totale app (misurato)** | **113.709** | 100% | 56.914 + 53.239 + 3.556 |

> **Ri-sommato il 3/09/2026, dopo R5 e R6.** Le tre righe fanno **113.576**
> contro un totale misurato di **113.709**: **133 righe di scarto**, che restano
> scritte qui invece di sparire in un arrotondamento. La riga «letto» non è un
> delta: viene dalla **ri-somma della colonna** frontend (27.515 su 20 aree).
>
> Lo scarto si scompone:
> - **100** righe di backend: i commenti aggiunti ai 12 router e ai 3 file di R6;
> - **27** righe di aree backend cresciute prima e mai ri-misurate;
> - **6** righe di frontend già dichiarate sopra.
>
> `100 + 27 + 6 = 133`. Se un giorno non torna, manca una misura.
>
> ⚠️ **Il totale è misurato su HEAD + solo il lavoro di questa sessione**, non
> sul working tree. Mentre R5/R6 chiudevano, un'altra sessione aveva **163 righe
> di frontend non committate** nell'albero: contarle qui avrebbe attribuito a
> questo ciclo lavoro di qualcun altro, e le sarebbe state contate due volte al
> suo commit. La prima stesura lo faceva, e le dava per «committate» quando non
> lo erano — corretto dal `code-reviewer`, poi ri-misurato.
>
> **La regola che genera questi scarti se la si viola:** ri-somma la colonna, non
> aggiungere il tuo delta. **La prima stesura di questa tabella aveva tre cifre
> stimate a occhio** — 30.749 / 47.157 / 35.463, che non tornavano con nessuna
> sezione sopra. È lo stesso errore che il file documenta da tre cicli, commesso
> mentre lo si riscriveva.

Quel che è letto è però il perimetro più esposto: ingresso dati, auth, DB,
Edge Functions, le 170 route, il MOL.

> **Queste righe si ricalcolano, non si ritoccano.** Il 31/8 una correzione è
> stata riportata qui a mano invece di rifare la somma: il risultato dichiarava
> 23.600 righe lette mentre le sezioni ne contavano 37.215 — e il file che esiste
> per far tornare i conti era l'unico posto dove non tornavano. Né
> `check_documentazione.py` né `test_documentazione_onesta.py` controllano
> l'aritmetica: qui la rete automatica non c'è.

---

## Cosa questo conto fa emergere

1. **`config/` (2.379) contiene i prompt AI** — la regola di dominio n.1 — e non
   è mai stato guardato.
2. **`worker/` (2.400) gira non presidiato** e non è in nessuna lista.
3. **`daily_briefing_service.py` (1.637)** ha avuto 4 sessioni di lavoro a
   settembre ma non è mai stato auditato come oggetto proprio.
4. **I `routers/` sono il blocco più grande a copertura parziale** (16.617 righe,
   ~4.000 lette).

---

## Come si aggiorna

A fine sessione: sposta la riga (🔴 → 🔍 → 📖), **ri-misura** coi comandi in cima,
poi **ri-somma la colonna** e controlla che chiuda col totale. Se un'area viene
esclusa, la ragione va scritta qui, non in un verbale che nessuno riapre.

## Lezioni che questo file ha pagato

- **Un delta non è una somma.** Tre stesure hanno aggiunto il proprio delta senza
  ri-sommare: tre totali diversi nello stesso documento.
- **Accettare una correzione non è verificarla.** Una cifra corretta da un
  reviewer e accettata senza ri-misurare è stata poi giustificata con una causa
  inventata («file senza newline finale»): non ce n'era nemmeno uno, e nessuno dei
  due numeri era quello vero. Lo scarto stava nel perimetro (gli `.svg`).
- **Un'estrazione non è a somma zero.** Il modulo estratto aggiunge firme, tipi e
  commenti che nel `.tsx` non esistevano: chi si aspetta il pareggio crede di aver
  sbagliato la misura.
- **Ri-misura contro HEAD, non contro il commit precedente al tuo.**
