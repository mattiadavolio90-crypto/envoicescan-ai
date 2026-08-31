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
| Frontend (`apps/web/src/`) | 51.055 |
| Edge Functions (`supabase/functions/`) | 3.556 |
| **TOTALE APP** | **110.061** |

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

## Frontend — 50.958 righe

> **Corretto il 31/8 dopo il `code-reviewer`.** La prima stesura dava 🔴 «mai
> guardata» a sette aree che i cicli 07 e 08 avevano già letto. La tabella §3c
> del ciclo 07 elenca **11 file su 11 letti riga per riga** in 4 passate
> (Margini · Scadenziario+Articoli · Tag+Prezzi · Workspace+Admin+mobile); il
> ciclo 08 ha chiuso **F3** (`components/`) e **F6** (`workspace/`). Le righe
> «lette» qui sotto sono quelle dichiarate in quei verbali.
>
> Misura sul tree **committato** (`git archive HEAD`): 50.958. Un `find` sul
> working tree può dare di più se una sessione parallela ha modifiche aperte.

| Area | Lette | Totali | Stato | Riferimento |
|---|---:|---:|---|---|
| `app/api/` — 169 route | 4.849 | 4.849 | 📖 | ciclo 08, 30/8 — proxy trasparente, 0/169 toccano il DB |
| `(app)/scadenziario/` | 2.212 | 2.212 | 📖 **100%** | ciclo 07 §3c + **chiusa 31/8 (2ª sess.)**: filtri/ordinamento/stato estratti in `lib/`, 15/15 mutanti. Resta il solo rendering |
| `(app)/analisi-e-tag/` | 1.392 | 1.518 | 📖 91% | ciclo 07 §3c |
| `(app)/margini/` | 2.903 | 4.795 | 🟠 60% | ciclo 07 §3c: calcolo-tab, analisi-tab, coperti-tab |
| `(app)/admin/` | 1.739 | 3.685 | 🟠 47% | ciclo 07 §3c: categorie + cliente-dettaglio |
| `(app)/prezzi/` | 973 | 2.361 | 🟠 41% | ciclo 07 §3c: variazioni-tab |
| `(app)/workspace/` | 1.834 | 5.012 | 🟠 37% | ciclo 07 §3c (personale-tab) + **F6 ciclo 08 CHIUSA**: il resto escluso con misura di esposizione live |
| `(mobile)/` | 1.270 | 3.984 | 🟠 32% | ciclo 07 §3c: mobile-turni |
| `(app)/analisi-fatture/` | 809 | 2.666 | 🟠 30% | ciclo 07 §3c: articoli-tab |
| `components/` | 2.188 | 7.298 | 🟠 30% | **F3 ciclo 08 CHIUSA**: 2.188 lette, 2.414 campionate, 2.675 escluse con misura |
| `lib/` | ~590 | 3.633 | 🟠 16% | solo `scadenziario.ts` (433 righe, +188 il 31/8) |
| `(app)/catena/` | 0 | 3.127 | 🔴 | **l'unica area grande che nessuna passata ha mai toccato** — multi-sede |
| `(app)/` — altre 4 aree | 0 | ~2.600 | 🔴 | dashboard, impostazioni, agenda, notifiche |
| `(auth)+(legal)+(demo)` | 0 | 1.353 | 🔴 | — |

**📖 letto: ~8.500 (17%) · 🟠 parziale: ~15.700 (31%) · 🔴 mai: ~7.100 (14%)**

Le righe non lette dentro un'area 🟠 non sono terra vergine: una passata ha
delimitato il perimetro e **motivato l'esclusione** (di solito: esposizione live
bassa). Rileggerle da zero è il lavoro fantasma che il metodo vieta.

## Edge Functions — 3.556 righe

📖 **Copertura completa e verificata** (13/13 file, 2 passate, ciclo 07).
È l'unico perimetro dove «completo» è stato controllato file per file.

---

## Il conto onesto

| | Righe | % |
|---|---:|---:|
| 📖 Letto integralmente | ~23.600 | **21%** |
| 🔍 Auditato per dimensione | ~17.650 | 16% |
| 🔴 Mai guardato | ~68.800 | **63%** |

Quel che è letto è però il perimetro più esposto: ingresso dati, auth, DB,
Edge Functions, 169 route.

---

## Cosa questo conto ha fatto emergere

> Nota di metodo: la prima stesura di questa sezione conteneva **due
> affermazioni false su tre** — diceva che `workspace/` e `margini/` non
> comparivano in nessuna tabella, mentre i verbali dei cicli 07 e 08 le
> avevano già lette in parte. Le ho scritte senza aprire i verbali, che è
> esattamente l'errore che il contatore esiste per impedire. Restano queste,
> verificate:

1. **`(app)/catena/` (3.127 righe) è l'unica area frontend grande che nessuna
   passata ha mai toccato.** Gestisce il multi-sede.
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
