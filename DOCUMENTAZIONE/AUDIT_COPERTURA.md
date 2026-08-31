# Copertura audit — il contatore

> **A cosa serve.** I cicli 2026-07 e 2026-08 hanno chiuso molte dimensioni, ma
> nessun documento sommava le righe: si sapeva **cosa** era stato chiuso, non
> **quanto mancava**. Da qui l'idea che «luglio + agosto coprano tutta l'app».
> Questo file è l'unico posto dove le somme devono tornare.

**Misurato il 31/08/2026.** Le cifre si **ri-misurano** a ogni aggiornamento,
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
| Frontend (`apps/web/src/`) | 50.958 |
| Edge Functions (`supabase/functions/`) | 3.556 |
| **TOTALE APP** | **109.964** |

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

| Area | Righe | Stato | Note |
|---|---:|---|---|
| `app/api/` — 169 route | 4.849 | 📖 coperto | ciclo 08, 30/8: proxy trasparente, 0/169 toccano il DB |
| `(app)/scadenziario/` | 2.303 | 🟠 parziale | backend+`lib/` coperti (77 test); **client 2.210 righe 🔴** |
| `lib/` | 3.445 | 🟠 parziale | solo `scadenziario.ts` |
| **`(app)/workspace/`** | **5.012** | 🔴 | **l'area più grande dell'app** |
| **`(app)/margini/`** | **4.795** | 🔴 | **regola di dominio MOL** |
| **`(app)/admin/`** | **3.685** | 🔴 | solo staff |
| **`(app)/catena/`** | **3.127** | 🔴 | multi-sede |
| **`(app)/analisi-fatture/`** | **2.666** | 🔴 | filtro "Da Classificare" |
| **`(app)/prezzi/`** | **2.361** | 🔴 | 39.133 righe fattura a monte |
| **`(app)/` — altre 7 aree** | **~5.700** | 🔴 | dashboard, analisi-e-tag, impostazioni, agenda, notifiche, assistenza, style-guide |
| **`components/`** | **7.298** | 🔴 | condivisa da tutte le pagine |
| **`(mobile)/`** | **3.984** | 🔴 | frontend separato, non responsive |
| `(auth)+(legal)+(demo)` | 1.353 | 🔴 | — |

**📖 coperto: ~4.900 (10%) · 🔴 mai: ~43.800 (86%)**

Il ciclo 07 lo dichiara: *«Frontend Next.js, 49.635 righe, 395 file — mai letto
riga per riga da nessuna dimensione»*. Resta vero.

---

## Edge Functions — 3.556 righe

📖 **Copertura completa e verificata** (13/13 file, 2 passate, ciclo 07).
È l'unico perimetro dove «completo» è stato controllato file per file.

---

## Il conto onesto

| | Righe | % |
|---|---:|---:|
| 📖 Letto integralmente | ~21.400 | **19%** |
| 🔍 Auditato per dimensione | ~17.650 | 16% |
| 🔴 Mai guardato | ~70.900 | **65%** |

Il 19% letto è però il più esposto: ingresso dati, auth, DB, Edge Functions,
169 route.

---

## Le tre cose che questo conto ha fatto emergere

1. **`workspace/` (5.012) e `margini/` (4.795) sono le due aree frontend più
   grandi e non compaiono in nessuna tabella.** La tabella «perimetro scoperto»
   del ciclo 08 elenca 4 aree su 14, e non queste. `margini/` tocca il MOL.
2. **`worker/` (2.353) gira non presidiato** e non è in nessuna lista.
3. **`config/` (2.334) contiene i prompt AI** — la regola di dominio n.1 — e non
   è mai stata guardata.

---

## Come si aggiorna

A fine sessione: sposta la riga (🔴 → 🔍 → 📖), **ri-misura** con i comandi in
cima, ricontrolla che le somme tornino. Se un'area viene **esclusa**, la ragione
va scritta qui, non in un verbale che nessuno riapre.
