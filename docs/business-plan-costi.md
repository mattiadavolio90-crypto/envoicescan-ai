# ONEFLUX — Business Plan dei Costi

*Documento interno · giugno 2026 · tutti i prezzi sono +IVA*

---

## 0. Gestione storage Supabase — già in opera + da rafforzare

Lo storage è il principale rischio di costo che cresce nel tempo. Stato attuale e piano:

**Già implementato (riduce il rischio):**
- **Purge XML automatico:** gli XML grezzi delle fatture vengono azzerati (`xml_content = NULL`, `xml_purged_at`) dopo il processing, via trigger DB + funzione dedicata. I file non si accumulano sullo storage.
- **Soft delete + cestino:** `deleted_at` su `fatture`/`prodotti`; il cestino consente l'hard delete reale.
- Nessun upload di PDF/XML su Supabase Storage: i file sono processati al volo, non archiviati.

**Da integrare (ottimizzazione storage a regime):**
1. **Hard-delete schedulato del cestino:** dopo N giorni in cestino → rimozione fisica (oggi resta soft).
2. **Archiviazione/compressione dati vecchi:** righe fattura oltre 24 mesi → tabella di archivio compressa o export, fuori dal DB caldo.
3. **Purge code processate:** `fatture_queue` con `processed_at` vecchio → eliminazione (indice GDPR già presente).
4. **Monitoraggio storage:** alert quando il DB supera ~6 GB (75% degli 8 GB inclusi nel Pro) per agire prima dell'overage.

> Con questi accorgimenti il DB cresce di ~2 GB/anno a 100 clienti e resta sotto gli 8 GB inclusi per 2-3 anni, senza salto al piano Team.

---

## 1. Costi fissi di infrastruttura

Costi sostenuti indipendentemente dal numero di clienti (piani superiori già attivi).

I costi fissi NON sono tutti uguali: alcuni sono davvero fissi, altri **scalano col consumo**. Verifica su piani ufficiali 2026.

| Voce | 0-20 clienti | 50 clienti | 100 clienti | Tipo |
|---|---|---|---|---|
| Railway (worker FastAPI) | €10 | €30 | €55 | ⚠️ scala col compute (parsing+AI) |
| Supabase (DB + Storage) | €25 | €30 | €38 | ⚠️ +overage DB (righe fatture) |
| Vercel (frontend Next.js) | €20 | €20 | €20 | ✅ fisso (1TB banda basta) |
| Aruba (dominio + email) | €5 | €5 | €5 | ✅ fisso |
| Brevo (email transazionali) | €0 | €0 | €9 | ⚠️ Starter oltre 300 email/giorno |
| AI sviluppo | €140 | €140 | €140 | ✅ fisso (comprimibile) |
| **TOTALE FISSO** | **€200** | **€225** | **€267** | |

**Perché scalano (o no):**
- **Railway** non ha piani: paghi il compute reale. Più clienti = più fatture processate = più CPU/RAM. È l'unico fisso che cresce in modo marcato.
- **Supabase** Pro €25 include 8 GB DB + 100 GB storage + 250 GB egress. Lo **storage file resta quasi vuoto** (gli XML vengono purgati dopo il processing, vedi §0). Cresce solo il DB con le righe fattura (~2 GB/anno a 100 clienti): overage modesto pay-as-you-go ($0,021/GB), NON serve il piano Team ($599).
- **Vercel** Pro €20 include 1 TB banda: i ristoratori generano pochissimo traffico, anche a 100 clienti si resta dentro. **Non scala** → resta €20.
- **Brevo** free = 300 email/giorno: a ~80+ clienti (reset, notifiche, attivazioni) si sfora → Starter €9.
- Tutti i prezzi sono in USD convertiti ~1:1 (prudente; €1 ≈ $1,08 reale).

---

## 2. Costi variabili per cliente

Scalano con l'uso di ciascun cliente.

### AI Categorizzazione — gpt-4o-mini (~750 token/fattura)

| Piano | Limite doc/mese | Costo AI cat. |
|---|---|---|
| Base | 50 | €0,08 |
| Plus | 100 | €0,16 |
| Pro | 200 | €0,32 |

### AI Assistente Chat — gpt-4.1-mini (~600 token/domanda)

| Piano | Domande/giorno | Costo max chat/mese |
|---|---|---|
| Base | 10 | €0,67 |
| Plus | 20 | €1,33 |
| Pro | 30 | €2,00 |

### Invoicetronic — incluso nei piani, costo per fattura SDI

Il costo unitario scende all'aumentare del volume aggregato (tutti i clienti).

| Fascia acquisto | €/transazione | Clienti stimati |
|---|---|---|
| 1.000 tx | €0,10 | fino a ~20 |
| 5.000 tx | €0,06 | ~20–100 |
| 20.000 tx | €0,04 | 100+ |

### Variabile totale per cliente (worst case = tutte le fatture via SDI, fascia €0,10)

| Piano | AI cat. | AI chat | SDI max | **Var. tot./cliente** |
|---|---|---|---|---|
| Base €39 | €0,08 | €0,67 | €5,00 | **€5,75** |
| Plus €59 | €0,16 | €1,33 | €10,00 | **€11,49** |
| Pro €79 | €0,32 | €2,00 | €20,00 | **€22,32** |

---

## 3. Margine lordo per cliente (al netto solo dei variabili)

### Scenario base — senza Invoicetronic (caricamento manuale)

| Piano | Ricavo | Costi AI | Margine | % |
|---|---|---|---|---|
| Base €39 | €39 | €0,75 | €38,25 | **98%** |
| Plus €59 | €59 | €1,49 | €57,51 | **97%** |
| Pro €79 | €79 | €2,32 | €76,68 | **97%** |

### Scenario worst case — tutte le fatture via SDI (fascia €0,10)

| Piano | Ricavo | AI + SDI | Margine | % |
|---|---|---|---|---|
| Base €39 | €39 | €5,75 | €33,25 | **85%** |
| Plus €59 | €59 | €11,49 | €47,51 | **81%** |
| Pro €79 | €79 | €22,32 | €56,68 | **72%** ⚠ |

> Il margine lordo per cliente resta ≥80% tranne il Pro in fascia €0,10 con uso SDI massimo (fase early). Dalla fascia €0,06 in poi tutti i piani tornano sopra l'80%.

---

## 4. Breakeven point

Fisso €200/mese · ARPU mix realistico €52 (60% Base, 30% Plus, 10% Pro) · variabile realistico ~€4,50/cliente (SDI uso moderato) → margine netto ~€47,50/cliente.

**Breakeven = €200 / €47,50 ≈ 5 clienti paganti.**

| Mix | Margine netto/cliente | Clienti per breakeven |
|---|---|---|
| Tutti Base €39 | ~€36 | **6** |
| Tutti Plus €59 | ~€55 | **4** |
| Tutti Pro €79 | ~€72 | **3** |
| Mix realistico €52 | ~€47,50 | **5** |

---

## 5. Costi totali (fissi + variabili) e margine d'azienda

Mix realistico · ARPU €52 · variabile realistico €4,50/cliente · fisso a scaglioni (§1).

| Clienti | Ricavo/mese | Fissi | Variabili | Costi tot. | **Margine netto** | % margine |
|---|---|---|---|---|---|---|
| 4 | €208 | €200 | €18 | €218 | **−€10** | sotto BEP |
| 5 | €260 | €200 | €23 | €223 | **€37** | 14% — break-even |
| 10 | €520 | €205 | €45 | €250 | **€270** | 52% |
| 20 | €1.040 | €210 | €90 | €300 | **€740** | 71% |
| 30 | €1.560 | €218 | €135 | €353 | **€1.207** | 77% |
| 50 | €2.600 | €225 | €225 | €450 | **€2.150** | 83% |
| 100 | €5.200 | €267 | €450 | €717 | **€4.483** | 86% |

*(Fissi interpolati tra gli scaglioni €200 / €225 / €267)*

---

## 6. Incidenza dei costi fissi sul ricavo

| Clienti | Ricavo/mese | % fissi su ricavo | % variabili su ricavo | % margine |
|---|---|---|---|---|
| 5 | €260 | 77% | 9% | 14% |
| 10 | €520 | 39% | 9% | 52% |
| 20 | €1.040 | 20% | 9% | 71% |
| 30 | €1.560 | 14% | 9% | 77% |
| 50 | €2.600 | 9% | 9% | 83% |
| 100 | €5.200 | 5% | 9% | 86% |

> I costi fissi (€200 early → €267 a 100 clienti, di cui €140 = AI sviluppo) pesano molto fino a ~10 clienti, poi si diluiscono. A regime il driver di costo diventa la quota variabile (Invoicetronic) + il compute Railway che cresce.

---

## 7. Proiezione ricavi annui

| Target | Clienti | Ricavo annuo | Margine netto annuo (~) | Fase |
|---|---|---|---|---|
| **2026** | 20 | €12.480 | €9.000 | Break-even solido |
| **metà 2027** | 50 | €31.200 | €26.100 | Reddito principale |
| **fine 2027** | 100 | €62.400 | €54.600 | Business maturo |

---

## 8. Piano marketing — costi di acquisizione (CAC)

Terza categoria di costi, oltre a fissi e variabili: i **costi per acquisire nuovi clienti**. Strategia: i primi **30 clienti a costo zero** (passaparola + RECOMA); gli ADS (Meta + Google) si accendono **solo sopra i 30 clienti**, finanziati dal margine.

### Canali e CAC stimato

| Canale | CAC tipico | Note |
|---|---|---|
| Meta / Instagram | €40-60 | Target ristoratori, ampia portata |
| Google ADS | €70-100 | Intento alto, chi cerca soluzioni |
| **Blended (mix)** | **~€70** | Stima centrale di partenza |

> **CAC** = costo pubblicitario per ottenere 1 cliente pagante. Se spendi €700 in ADS e arrivano 10 clienti → CAC €70.

### Payback — quanto ci mette un cliente a ripagare il costo di acquisizione

| CAC | Margine/mese | Payback |
|---|---|---|
| €50 | ~€47 | ~1,1 mesi |
| €70 | ~€47 | ~1,5 mesi |
| €100 | ~€47 | ~2,1 mesi |

> Payback sotto 12 mesi è considerato sano per un SaaS. Qui è sotto i 3 mesi anche nello scenario peggiore: ogni euro speso in ADS rientra in fretta.

### Budget marketing per centrare i target — ADS solo sopra i 30 clienti

| Periodo | Canale | Nuovi clienti | Budget @ €50 | Budget @ €70 | Budget @ €100 |
|---|---|---|---|---|---|
| 2026 → 20 clienti | Passaparola + RECOMA | 18 | €0 | €0 | €0 |
| inizio 2027 → 30 | Passaparola + RECOMA | 10 | €0 | €0 | €0 |
| metà 2027 → 50 | ADS Meta + Google | 20 | €1.000 | €1.400 | €2.000 |
| fine 2027 → 100 | ADS Meta + Google | 50 | €2.500 | €3.500 | €5.000 |
| **TOTALE (100 clienti)** | — | **98** | **€3.500** | **€4.900** | **€7.000** |

> **Strategia:** i primi **30 clienti a costo marketing zero** — tutta crescita organica (passaparola + RECOMA) fino a fine 2026 / inizio 2027. Gli **ADS si accendono solo da 30 clienti in poi**, quando il margine mensile (~€1.000+) finanzia la pubblicità senza intaccare la cassa. Il salto 30→100 costa tra **€3.500 e €7.000** totali, ampiamente coperto dal margine di quei mesi.

---

## Note operative

- **Breakeven a 5 clienti** col fisso €200. A 4 clienti si è ancora in lieve perdita (−€10/mese). I primi clienti coprono soprattutto i €140 di AI sviluppo: è la voce fissa dominante in fase early.
- **Solo Railway scala davvero** tra i fissi (compute del worker). Supabase/Vercel/Brevo restano sotto controllo grazie al purge XML già attivo e ai limiti ampi dei piani Pro. Nessun salto a piani superiori (Team €599, Vercel Enterprise) previsto fino a centinaia di clienti.
- **Invoicetronic** è incluso nei piani: monitorarlo per cliente. Scalando alle fasce €0,06 / €0,04 (più clienti = volume aggregato) il costo unitario crolla e i margini migliorano automaticamente.
- **AI sviluppo €140** è l'unico fisso comprimibile: se in futuro non serve più sviluppo intensivo, il fisso scende a €60 e il breakeven a ~2 clienti.
- **Da chiarire:** chi incassa gli abbonamenti (RECOMA vs incasso diretto) — se via Stripe/carta aggiungere ~€1-1,50/cliente/mese di commissioni ai variabili. Oggi non modellato.
- **Rischio principale:** non i costi (margini >80% da ~50 clienti) ma la velocità di acquisizione. Sotto i 10 clienti il margine netto è sottile.
