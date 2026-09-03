# Copertura audit — il contatore

> **A cosa serve.** È l'unico posto dove si risponde a «quanta dell'app è stata
> davvero controllata». I cicli chiudono dimensioni, ma nessun altro documento
> somma le righe: senza questo file si sa *cosa* è stato chiuso, non *quanto*
> manca. **È anche l'unico posto dove le somme devono tornare.**

**Ri-misurato il 3/09/2026.** Le cifre si ri-misurano a ogni aggiornamento, mai
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
| Backend Python (`services/`, `utils/`, `config/`, `worker/`) | 57.263 |
| Frontend (`apps/web/src/`, esclusi i binari) | 53.764 |
| Edge Functions (`supabase/functions/`) | 3.556 |
| **TOTALE APP** | **114.583** |

> Ri-misurato il 3/9 a fine sessione «tutte le voci» (voci §3 #2→#6). Il
> frontend è cresciuto di ~500 righe fra commit paralleli e card Fase 4bis: la
> tabella per aree chiudeva a 53.233 prima — la ri-somma per area spetta alla
> prossima sessione frontend.

---

## Backend Python — 57.263 righe

| Modulo | Righe | Stato | Riferimento |
|---|---:|---|---|
| `db_service.py` | 2.284 | 📖 letto | ciclo 07, 8/8; 3/9 helper Fase 4 (`escludi_da_verificare_margini`, `rpc_params_fase4`) |
| `invoice_service.py` | 2.333 | 📖 letto | ciclo 07, 10/8 |
| `auth_service.py` | 1.782 | 📖 letto | ciclo 07, 8/8 |
| `ai_service.py` | 5.742 | 📖 nucleo decisione + gate | ciclo 09: motore unico, gate, 9 uscite. 101 test |
| `upload_handler.py` | 2.282 | 🔍 chiamante del gate | passa descrizione e fornitore a `valuta_fiducia` |
| `margine_service.py` | 1.487 | 🔍 di rimbalzo | **regola di dominio MOL**; 3/9 il filtro «Da Classificare» viene dalla costante (R6) |
| `fastapi_worker.py` | 8.899 | 🔍 per router | voce Salute coperta con 10 test dopo il bug del 2/9; 3/9 le 4 copie del filtro «Da Classificare» legate alla costante (R6) |
| `daily_briefing_service.py` | 1.656 | 📖 letto | voce §3 #4, 3/9 sera: letto integralmente, 2 fix (formato scadenze, validatore tono v21), 3/3 mutanti. Report: `scratchpad/audit_briefing_report.md` |
| `routers/` (tutti) | 16.701 | 🟠 parziale | ~4.000 letti nel ciclo 07 (workspace, tag, margini, ricavi, scadenziario); il resto no. 3/9: **216 endpoint su 216 ri-verificati protetti** e guardia a livello di router (R5) — il perimetro *sicurezza* è chiuso, quello *logica* no |
| `worker/` | 2.411 | 📖 letto | voce §3 #5, 3/9 sera: letto integrale — la premessa «non presidiato» era falsa. 1 latente chiuso (retry coda email), 1/1 mutanti. Report: `scratchpad/audit_worker_report.md` |
| `utils/` | 2.574 | 🔴 | — |
| `config/` | 2.411 | 🔍 auditato 3/9 | voce §3 #2: prompt letto integrale, dizionario validato al 100% via script (chiavi/valori/codifica), coerenza prompt↔costanti↔DB misurata. Fix: 12 chiavi mojibake. Report: `scratchpad/audit_prompt_ai_report.md` |
| `services/` (altri moduli) | 6.701 | 🔴 | riparto, foodcost, price_impact, radar… |

---

## Frontend — 53.239 righe

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

1. ~~`config/` contiene i prompt AI e non è mai stato guardato~~ — **auditato il
   3/9** (voce §3 #2): coerenza piena, un difetto di codifica chiuso con presidio.
2. ~~`worker/` gira non presidiato~~ — **letto integralmente il 3/9** (voce §3
   #5): era il contrario, è tra i moduli più difesi; 1 latente chiuso.
3. ~~`daily_briefing_service.py` mai auditato come oggetto proprio~~ — **letto
   integralmente il 3/9** (voce §3 #4): l'impianto regge, 2 fix minori.
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
