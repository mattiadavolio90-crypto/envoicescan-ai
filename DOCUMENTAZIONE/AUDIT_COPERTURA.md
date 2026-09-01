# Copertura audit — il contatore

> **A cosa serve.** I cicli 2026-07 e 2026-08 hanno chiuso molte dimensioni, ma
> nessun documento sommava le righe: si sapeva **cosa** era stato chiuso, non
> **quanto mancava**. Da qui l'idea che «luglio + agosto coprano tutta l'app».
> Questo file è l'unico posto dove le somme devono tornare.

**Misurato il 31/08/2026** (ri-misurato a fine sessione scadenziario). Le cifre si **ri-misurano** a ogni aggiornamento,
mai ereditate da qui:

```bash
find services utils config worker -name "*.py" | xargs wc -l | tail -1
find apps/web/src -name "*.tsx" -o -name "*.ts" | xargs wc -l | tail -1
```

---

## Due modi diversi di essere «coperto»

La distinzione che i cicli fanno nei fatti ma nessuna tabella rendeva visibile:

- **📖 Letto integralmente** — qualcuno ha letto il file riga per riga e lo ha
  dichiarato (`2242/2242 righe lette`). È la copertura forte.
- **🔍 Auditato per dimensione** — il modulo è passato sotto una lente
  specifica (Security, Bug, AI, Performance…). Trova i difetti *di quella
  classe*; non dice nulla sulle altre. Luglio lo scrive da sé: la prima passata
  su `ai_service.py` lasciò **~3.900 righe non lette**, e il secondo giro trovò
  lì l'HIGH più grave del ciclo.
- **🔴 Mai guardato** — non compare in nessuna passata.

---

## Il totale

| Perimetro | Righe |
|---|---:|
| Backend Python (`services/`, `utils/`, `config/`, `worker/`) | 55.450 |
| Frontend (`apps/web/src/`) | 51.413 |
| Edge Functions (`supabase/functions/`) | 3.556 |
| **TOTALE APP** | **110.419** |

---

## Backend Python — 55.450 righe

| Modulo | Righe | Stato | Riferimento |
|---|---:|---|---|
| `db_service.py` | 2.249 | 📖 letto (2242/2242) | ciclo 07, 8/8 |
| `invoice_service.py` | 2.231 | 📖 letto (2174/2174) | ciclo 07, 10/8 |
| `auth_service.py` | 1.782 | 📖 letto (1718/1718) | ciclo 07, 8/8 |
| `documenti_service.py` | 1.096 | 📖 letto (1582/1582 doc+router) | ciclo 07, 11/8 |
| `tag_suggestion_service.py` | 1.087 | 📖 letto (1019/1019) | ciclo 07, 24/8 |
| `tag_analytics_service.py` | 488 | 📖 letto | ciclo 07, 24/8 |
| `routers/` — workspace, tag, margini, ricavi, scadenziario | ~4.000 | 📖 letti | ciclo 07 |
| `ai_service.py` | 5.405 | 🔍 dimensione AI, 2 passate | HIGH#1 trovato al 2º giro |
| `upload_handler.py` | 2.222 | 🔍 di rimbalzo (22 citazioni) | mai come oggetto proprio |
| `margine_service.py` | 1.476 | 🔍 di rimbalzo (15 citazioni) | **regola di dominio MOL** |
| `fastapi_worker.py` | 8.551 | 🔍 per router, non come oggetto | ciclo 07 |
| **`routers/` (restanti ~15)** | **~12.400** | 🔴 | — |
| **`worker/`** | **2.353** | 🔴 | queue-worker, gira non presidiato |
| **`utils/`** | **2.574** | 🔴 | — |
| **`config/`** | **2.334** | 🔴 | contiene i prompt AI |
| **`daily_briefing_service.py`** | **1.356** | 🔴 (3 citazioni) | — |
| **`services/` (altri ~20 moduli)** | **~4.400** | 🔴 | riparto, foodcost, price_impact, radar… |

**📖 letto: ~12.900 (23%) · 🔍 per dimensione: ~17.650 (32%) · 🔴 mai: ~24.900 (45%)**

---

## Frontend — 51.063 righe

> **Corretto il 31/8 dopo il `code-reviewer`.** La prima stesura dava 🔴 «mai
> guardata» a sette aree che i cicli 07 e 08 avevano già letto. La tabella §3c
> del ciclo 07 elenca **11 file su 11 letti riga per riga** in 4 passate
> (Margini · Scadenziario+Articoli · Tag+Prezzi · Workspace+Admin+mobile); il
> ciclo 08 ha chiuso **F3** (`components/`) e **F6** (`workspace/`). Le righe
> «lette» qui sotto sono quelle dichiarate in quei verbali.
>
> Misura sul tree **committato** (`git archive HEAD`, **meno le 481 righe dei due
> font `.woff` binari** che il tar include): **52.226** a HEAD, ri-misurata l'1/9
> alla 3ª sessione catena. La 1ª passata aveva portato 51.614 (+201: `lib/` +284,
> `(app)/catena/` −83); la 2ª +591; la 3ª porterà **+171** (`catena-export.ts`
> +194, i due `.tsx` −23) → **52.397** dopo il commit.
>
> ⚠️ Il 52.205 scritto qui a mezzogiorno dell'1/9 era già vecchio due ore dopo:
> **una sessione parallela ha committato nel frattempo**. La cifra a HEAD si
> ri-misura quando la si scrive, sempre — non si eredita dalla riga sopra. Un
> `find` sul working tree dà di più ancora se una sessione ha modifiche aperte.
>
> ⚠️ **+284 e −83 non si compensano: un'estrazione NON è a somma zero.** Il
> modulo estratto aggiunge firme, tipi e i commenti che spiegano ogni anomalia
> fotografata — righe che nel `.tsx` non esistevano. Chi ri-somma aspettandosi il
> pareggio trova un delta e crede di aver sbagliato la misura: è il contrario,
> il delta è il lavoro. Ri-somma sempre la colonna e confrontala con
> `find apps/web/src -type f ! -name '*.woff' | xargs wc -l`.
>
> ⚠️ **Il totale precedente (51.063) era sbagliato di 350 righe, e non per il
> refactor.** Ri-sommando la colonna a HEAD sono emerse due cose: la voce
> `hooks/`+`proxy.ts`+file diretti valeva **622**, non 312 (i file diretti in
> `app/` sono 495, di cui 296 di solo `globals.css`, non 185); e `app/fonts/`
> contiene **due `.woff` binari** che `wc -l` conta come 481 "righe" pur non
> essendo codice — ora esclusi esplicitamente dal totale. La cifra girava da
> almeno due cicli. `git archive HEAD apps/web/src | tar -xO | wc -l` dà 51.894:
> è 51.413 **più i 481 dei font**.
>
> ⚠️ **Ri-misura contro HEAD, non contro il commit precedente al tuo.** Il 31/8
> è successo due volte di fila: la cifra veniva aggiornata al valore giusto per
> il commit *prima* dell'ultimo, e restava stantia di 8 righe. Il `code-reviewer`
> l'ha intercettata entrambe le volte — `check_documentazione.py` non controlla
> l'aritmetica, quindi qui la rete automatica non c'è.

| Area | Lette | Totali | Stato | Riferimento |
|---|---:|---:|---|---|
| `app/api/` — 169 route | 4.849 | 4.849 | 📖 | ciclo 08, 30/8 — proxy trasparente, 0/169 toccano il DB |
| `(app)/scadenziario/` | 2.211 | 2.211 | 📖 **100%** | ciclo 07 §3c + **chiusa 31/8 (2ª sess.)**: filtri/ordinamento/stato estratti in `lib/`, 15/15 mutanti. Resta il solo rendering |
| `(app)/analisi-e-tag/` | 1.392 | 1.518 | 📖 91% | ciclo 07 §3c |
| `(app)/margini/` | 4.709 | 4.709 | 📖 **100%** | ciclo 07 §3c + **chiusa 31/8 (3ª sess.)**: `fetchNettoMese`, `periodi.ts`, aggregati e pivot estratti in `lib/`, 183 test, 65/65 mutanti. Resta il solo rendering |
| `(app)/admin/` | 1.739 | 3.685 | 🟠 47% | ciclo 07 §3c: categorie + cliente-dettaglio |
| `(app)/prezzi/` | 973 | 2.361 | 🟠 41% | ciclo 07 §3c: variazioni-tab |
| `(app)/workspace/` | 1.834 | 5.012 | 🟠 37% | ciclo 07 §3c (personale-tab) + **F6 ciclo 08 CHIUSA**: il resto escluso con misura di esposizione live |
| `(mobile)/` | 1.270 | 3.984 | 🟠 32% | ciclo 07 §3c: mobile-turni |

> **Nota trasversale (1/9):** in `margini/`, `workspace/`, `prezzi/`, `dashboard/`
> e `(mobile)/` il **parsing degli importi digitati** è ora coperto anche dove la
> pagina non lo è: le 58 chiamate passano tutte da `lib/format.ts`, che ha 60
> test. Le percentuali di riga non cambiano — il fix ha sostituito chiamate, non
> estratto logica — ma il punto in cui un importo poteva essere letto mille volte
> più piccolo non è più scoperto in nessuna di queste aree.
| `(app)/analisi-fatture/` | 809 | 2.666 | 🟠 30% | ciclo 07 §3c: articoli-tab |
| `components/` | 2.188 | 7.298 | 🟠 30% | **F3 ciclo 08 CHIUSA**: 2.188 lette, 2.414 campionate, 2.675 escluse con misura |
| `lib/` | 1.700 | 4.805 | 🟠 35% | `scadenziario.ts` (442) + `margini-aggregati.ts` (126) + `catena-confronti.ts` (318) + `catena-tag.ts` (229) + `catena-costi-gruppo.ts` (173) + `catena-export.ts` (211) + `tag-candidati.ts` (61) + **`format.ts` (140)**. `format.ts` è entrato l'1/9 col fix sugli importi italiani: 60 test, è la **fonte unica** del parsing numerico per tutta l'app (58 chiamanti) |
| `(app)/catena/` | 2.800 | 2.938 | 🟢 95% | **CHIUSA l'1/9 in tre passate**: 7 file su 9 con logica in `lib/` (`catena-confronti.ts`, `catena-tag.ts`, `catena-costi-gruppo.ts`, `catena-export.ts`). **283 test** = confronti 95 + tag 61 + costi 50 + export 64 + `tag-candidati` 13 (quest'ultimo è di catena: estratto da `gruppo-tag-section.tsx` nella 1ª passata). **Non** include i 18 di `test_helpers_ts_harness.py`, che testano l'harness, non `catena/`. Bilancio mutazione **per passata** nel verbale (la 3ª: 41 mutanti, 38 uccisi, 3 equivalenze) — non sommato qui, perché i cataloghi delle prime due sono cresciuti in review e un totale aggregato sarebbe un numero che nessuno ha misurato. Scoperte **138 righe**, entrambe senza logica: `card-segnali.tsx` 110 (fetch + JSX, `ICONA` mappa a componenti lucide) + `loading.tsx` 28 (skeleton). `page.tsx` è stato chiuso estraendo le sue due decisioni (`num_pv < 2 → redirect`, pool chat `> 0`) come predicati puri. **Copre la logica pura, non il rendering** |
| `(app)/` — altre 7 aree + file diretti | 0 | 4.250 | 🔴 | misurate il 31/8: dashboard 1.749 · impostazioni 806 · agenda 693 · notifiche 339 · assistenza 292 · style-guide 256 · file diretti 115 |
| `hooks/` + `proxy.ts` + file diretti in `app/` | 0 | 622 | 🔴 | **ri-misurati il 31/8: 22 + 105 + 495** — i file diretti erano contati 185, sono 495 (`globals.css` da solo ne fa 296) |
| `(auth)`+`(legal)`+`(demo)` — dettaglio | — | 1.353 | 🔴 | 552 + 575 + 226 |

**Righe lette: 24.343 · non lette: 27.271 · totale 51.614** — la tabella copre
tutto `apps/web/src`: la somma della colonna «Totale area» uguaglia
`git archive HEAD` **meno i 481 dei due font binari** (51.894 − 481 = 51.413).
Ri-verificato a ogni aggiornamento, **sommando le righe della tabella**, non
fidandosi della frase precedente — è così che è saltato fuori che 51.063 era
sbagliato di 350.

| | Lette | Totale area | Non lette |
|---|---:|---:|---:|
| 📖 aree complete | 13.161 | 13.287 | 126 |
| 🟠 aree parziali | 11.182 | 32.002 | 20.820 |
| 🔴 mai aperte | 0 | 6.325 | 6.325 |
| **totale** | **24.343** | **51.614** | **27.271** |

Le 126 righe non lette dentro le aree 📖 sono la differenza fra «area chiusa» e
«ogni riga letta»: `app/api/` è 4.849/4.849, `scadenziario/` 2.211/2.211,
`margini/` 4.709/4.709, ma `analisi-e-tag/` è 1.392/1.518. Un'area 📖 non è per
forza al 100%.

> «Area chiusa» significa **la logica pura è coperta e provata per mutazione**,
> non «ogni riga ha un test». In `margini/` le 4.709 righe sono state lette
> tutte, ma i test ne raggiungono ~400: il resto è JSX, hook, stato e recharts,
> che `esegui_ts` non sa montare — è un limite dell'infrastruttura, dichiarato,
> non una svista.

> La stesura precedente sommava `17% + 31% + 14% = 62%`: le tre voci misuravano
> grandezze diverse (righe lette, totali d'area, righe mai viste) e il 38%
> restante non stava da nessuna parte. Le percentuali qui sopra sono tutte sullo
> stesso denominatore — 51.063 righe di frontend — e chiudono a 100%.

Le righe non lette dentro un'area 🟠 non sono terra vergine: una passata ha
delimitato il perimetro e **motivato l'esclusione** (di solito: esposizione live
bassa). Rileggerle da zero è il lavoro fantasma che il metodo vieta.

## Edge Functions — 3.556 righe

📖 **Copertura completa e verificata** (13/13 file, 2 passate, ciclo 07).
È l'unico perimetro dove «completo» è stato controllato file per file.

---

## Il conto onesto

Somma delle tre sezioni sopra, non una stima a parte:

| | Righe | % | da dove viene |
|---|---:|---:|---|
| 📖 Letto integralmente | 39.155 | **35%** | 12.900 backend + 22.699 frontend + 3.556 Edge |
| 🔍 Auditato per dimensione | 17.650 | 16% | solo backend |
| 🔴 Mai guardato | 53.614 | **49%** | 24.900 backend + 28.714 frontend |
| **Totale** | **110.419** | 100% | 55.450 + 51.413 + 3.556 |

Quel che è letto è però il perimetro più esposto: ingresso dati, auth, DB,
Edge Functions, 169 route.

> **Queste tre righe si ricalcolano, non si ritoccano.** Il 31/8 la correzione
> di 7 aree frontend è stata riportata qui a mano (`19%` → `21%`) invece di
> rifare la somma: il risultato dichiarava 23.600 righe lette mentre le sezioni
> ne contavano 37.215, e il file che esiste per far tornare i conti era l'unico
> posto dove non tornavano. Trovato dal `code-reviewer`, non da un test — qui la
> rete automatica non c'è.

---

## Cosa questo conto ha fatto emergere

> Nota di metodo: la prima stesura di questa sezione conteneva **due
> affermazioni false su tre** — diceva che `workspace/` e `margini/` non
> comparivano in nessuna tabella, mentre i verbali dei cicli 07 e 08 le
> avevano già lette in parte. Le ho scritte senza aprire i verbali, che è
> esattamente l'errore che il contatore esiste per impedire. Restano queste,
> verificate:

1. ~~`(app)/catena/` è l'unica area frontend grande mai toccata~~ — **chiusa
   l'1/9 in tre passate**, 2.800/2.938 (95%). Le 138 righe residue non hanno
   logica: fetch, JSX e skeleton.
2. **`worker/` (2.353) gira non presidiato** e non è in nessuna lista.
3. **`config/` (2.334) contiene i prompt AI** — la regola di dominio n.1 — e non
   è mai stato guardato.
4. **Le aree 🟠 non vanno rilette da zero**: il perimetro escluso è stato
   *misurato e motivato* (di solito esposizione live bassa). Riaprirlo senza
   leggere il verbale è lavoro fantasma.

---

## Come si aggiorna

A fine sessione: sposta la riga (🔴 → 🔍 → 📖), **ri-misura** con i comandi in
cima, ricontrolla che le somme tornino. Se un'area viene **esclusa**, la ragione
va scritta qui, non in un verbale che nessuno riapre.
