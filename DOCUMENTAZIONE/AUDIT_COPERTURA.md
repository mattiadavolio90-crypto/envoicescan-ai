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
| Backend Python (`services/`, `utils/`, `config/`, `worker/`) | 56.814 |
| Frontend (`apps/web/src/`, esclusi i binari) | 53.031 |
| Edge Functions (`supabase/functions/`) | 3.556 |
| **TOTALE APP** | **113.369** |

---

## Backend Python — 56.814 righe

| Modulo | Righe | Stato | Riferimento |
|---|---:|---|---|
| `db_service.py` | 2.249 | 📖 letto | ciclo 07, 8/8 |
| `invoice_service.py` | 2.333 | 📖 letto | ciclo 07, 10/8 |
| `auth_service.py` | 1.782 | 📖 letto | ciclo 07, 8/8 |
| `ai_service.py` | 5.715 | 📖 nucleo decisione + gate | ciclo 09: motore unico, gate, 9 uscite. 101 test |
| `upload_handler.py` | 2.282 | 🔍 chiamante del gate | passa descrizione e fornitore a `valuta_fiducia` |
| `margine_service.py` | 1.476 | 🔍 di rimbalzo | **regola di dominio MOL** |
| `fastapi_worker.py` | 8.745 | 🔍 per router | voce Salute coperta con 10 test dopo il bug del 2/9 |
| `daily_briefing_service.py` | 1.637 | 🔍 di rimbalzo | 4 sessioni di lavoro a settembre sul briefing, mai auditato come oggetto proprio |
| `routers/` (tutti) | 16.514 | 🟠 parziale | ~4.000 letti nel ciclo 07 (workspace, tag, margini, ricavi, scadenziario); il resto no |
| `worker/` | 2.400 | 🔴 | queue-worker, **gira non presidiato** |
| `utils/` | 2.574 | 🔴 | — |
| `config/` | 2.379 | 🔴 | **contiene i prompt AI** — la regola di dominio n.1 |
| `services/` (altri moduli) | 6.701 | 🔴 | riparto, foodcost, price_impact, radar… |

---

## Frontend — 53.031 righe

> **Le somme di questa tabella chiudono a 52.949**, verificate contro
> `git ls-files` il 2/9. Le tre stesure precedenti non chiudevano: giravano tre
> totali diversi (51.413, 51.614, 52.998) nello stesso file, perché ogni sessione
> aggiungeva il proprio delta invece di ri-sommare la colonna. **Ri-somma sempre,
> non sommare delta.**

| Area | Lette | Totali | Stato | Riferimento |
|---|---:|---:|---|---|
| `app/api/` — 170 route | 4.871 | 4.871 | 📖 | ciclo 09, 30/8 — proxy trasparente, 0 route toccano il DB |
| `(app)/margini/` | 4.711 | 4.711 | 📖 | ciclo 09, 31/8 — 183 test, 65/65 mutanti. Resta il rendering |
| `(app)/scadenziario/` | 2.211 | 2.211 | 📖 | ciclo 09, 31/8 — 15/15 mutanti. Resta il rendering |
| `(app)/catena/` | 2.938 | 2.938 | 📖 100% | ciclo 09, 1/9 (3 passate) + 3/9 (R3). 290 test. `card-segnali.tsx` (110) è **esclusione motivata**, non un buco: fetch + JSX, provata da `test_catena_card_segnali_esclusione.py` (4/4 mutanti). Resta il rendering |
| `(app)/analisi-e-tag/` | 1.392 | 1.518 | 📖 92% | ciclo 07 §3c |
| `lib/` | 2.318 | 5.444 | 🟠 43% | i moduli estratti dalle sessioni di settembre; `format.ts` è la fonte unica del parsing numerico (58 chiamanti) |
| `(app)/admin/` | 1.739 | 3.871 | 🟠 45% | ciclo 07 §3c — solo staff, non clienti |
| `(app)/prezzi/` | 973 | 2.358 | 🟠 41% | ciclo 07 §3c |
| `(app)/workspace/` | 1.834 | 5.021 | 🟠 37% | ciclo 07 §3c + F6 ciclo 08: il resto escluso con misura |
| `(mobile)/` | 1.270 | 3.994 | 🟠 32% | ciclo 07 §3c |
| `(app)/analisi-fatture/` | 809 | 2.661 | 🟠 30% | ciclo 07 §3c |
| `components/` | 2.188 | 7.299 | 🟠 30% | F3 ciclo 08: 2.188 lette, 2.414 campionate, 2.675 escluse con misura |
| `(app)/dashboard/` | 0 | 1.685 | 🟠 logica estratta | 1/9: la logica è uscita nei moduli `home-*.ts`, 92 test. Nessun `.tsx` letto |
| `(app)/impostazioni/` | 0 | 808 | 🟠 logica estratta | 2/9: logica in `piani.ts` + `impostazioni-account.ts`, 22 test |
| `(app)/notifiche/` | 0 | 242 | 🟠 logica estratta | 2/9: logica in `notifiche-shared.ts`, 23 test |
| `(app)/agenda/` | 0 | 693 | 🔴 | **0 turni a DB**: scartata con misura, non dimenticata |
| `(app)/assistenza/` | 0 | 292 | 🔴 | `marketplace_leads` 0 righe |
| `(app)/style-guide/` | 0 | 256 | 🔴 | pagina interna |
| `(auth)` + `(legal)` + `(demo)` | 0 | 1.353 | 🔴 | 552 + 575 + 226 |
| `hooks/` + file diretti + proxy | 0 | 723 | 🔴 | include `globals.css` |

**Somma: lette 27.254 · non lette 25.695 · totale 52.949** (ri-sommata il
3/09/2026, non aggiornata per delta).

> ⚠️ **La tabella chiude a 52.949, il repo misura 53.031: mancano 82 righe.**
> Non è il mio delta (il lavoro del 3/09 vale +5 righe nette sul frontend): lo
> scarto c'era già e viene da aree cresciute senza che la loro riga fosse
> ri-misurata. Dichiarato invece che nascosto in un arrotondamento — chi
> ri-misura un'area, chiuda anche questo.

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
| 📖 Letto integralmente | 37.174 | **33%** | 6.364 backend + 27.254 frontend + 3.556 Edge |
| 🔍 / 🟠 Auditato o parzialmente coperto | 58.885 | 52% | 36.369 backend + 22.516 frontend |
| 🔴 Mai guardato | 17.371 | **15%** | 14.054 backend + 3.317 frontend |
| **Totale app (misurato)** | **113.401** | 100% | 56.814 + 53.031 + 3.556 |

> **Ri-sommato il 3/09/2026.** Le tre righe fanno **113.430** contro un totale
> misurato di **113.401**: **29 righe di scarto**, che restano scritte qui invece
> di sparire in un arrotondamento. Vengono da righe di area cresciute senza
> essere ri-misurate (lo stesso scarto di 82 righe dichiarato nella tabella
> frontend), non dal lavoro del 3/09, che vale +5 righe nette.
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
4. **I `routers/` sono il blocco più grande a copertura parziale** (16.514 righe,
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
