# Ripartizione costi di struttura sulle catene — PIANIFICAZIONE

> Stato: **PIANIFICAZIONE**, non implementato. Documento di decisione + disegno.
> Nessun codice scritto. Data: 1/7/2026 — Owner: Mattia.
> **Decisione presa: Proposta 2** (MOL onesto + finestra "Costi di gruppo" in catena).

---

## 1. Il problema

Nelle catene con più punti vendita (PV) esistono **costi di struttura** intestati
a *una* sede (o all'unica P.IVA, caso OFFSIDE) che in realtà servono **tutto il
gruppo**: commercialista, auto aziendale, telefonia, software, consulenze. Oggi
il costo entra intero nel MOL della sede intestataria → **MOL falsato**: quella
sede sembra meno redditizia, le altre più redditizie del vero.

Stesso problema per i **dipendenti d'ufficio** (lavorano per tutta la catena):
oggi si ripartiscono a mano, sede per sede — scomodo ma fattibile. Inclusi nella
stessa soluzione così si smette di farlo a mano.

Vale sia per fatture **SDI** che per fatture **caricate a mano**.

---

## 2. Principio guida (non negoziabile)

- **La fattura resta sacra.** Mai riscrivere/spezzare le righe di una fattura
  elettronica: integrità fiscale + quadratura + collegamento al documento.
- **Il motore MOL non cambia.** La ripartizione riusa la porta già esistente dei
  "costi non da fattura" → `altri_costi_spese` / `altri_costi_fb` di
  `margini_mensili` (oggi alimentata da `spese_extra`). Home, catena, briefing,
  grafici leggono la stessa cella di sempre: vedono un numero più completo.
- **Aggregazione, non loop** (regola catena): le quote si calcolano 1×/mese via
  RPC SQL, mai loop Python sulle righe.
- **Il cliente gestisce i suoi riparti** — solo lui sa cosa va diviso. Si aggancia
  a "Gestione fatture", dove già oggi può spostare una fattura tra PV
  (`/api/fatture/sposta-sede`).
- **Regole/AI propongono, il cliente decide** (filosofia ONEFLUX): la regola
  fornitore *propone* un riparto, non lo applica da sola.

---

## 3. Scelta di profondità — PROPOSTA 2 (decisa)

Tre livelli erano possibili:
- **P1 — solo MOL:** MOL onesto ma nessuna schermata mostra *come* è diviso.
- **P2 — MOL + finestra dedicata (SCELTA):** MOL onesto + una finestra in catena
  che elenca i costi ripartiti, le quote per sede e la regola. L'incoerenza con
  Analisi Fatture resta ma è **spiegata** da una vista apposita.
- **P3 — visibile ovunque (rimandata):** anche Analisi Fatture (Articoli/Categorie/
  Fornitori) mostrerebbe la quota invece dell'intero. Massima coerenza ma
  intervento invasivo sulle viste di analisi → dopo il go-live, se serve.

**Nota di coerenza (accettata):** con P2, in **Analisi Fatture** la fattura di
struttura resta **intera sulla sede intestataria** (quelle viste leggono
`fatture` per `ristorante_id`). Il MOL invece la vede divisa. La finestra "Costi
di gruppo" + la nota nel dettaglio fattura (§7) rendono questa differenza
comprensibile.

---

## 4. Modello dati

Tabelle nuove a livello **account** (non sede):

```
riparto_costi_catena
  id, user_id (account)
  origine        -- 'fattura' | 'manuale'
  file_origine   -- se da fattura; NULL se voce manuale (es. stipendi ufficio)
  descrizione    -- "Commercialista giugno", "Stipendi ufficio"
  importo_totale
  tipo           -- 'generale' | 'fb'  (quale cella del MOL alimenta)
  anno, mese     -- competenza
  regola         -- 'equa' | 'percentuali'
  created_at, updated_at

riparto_costi_catena_quote
  riparto_id, ristorante_id, quota_perc, quota_importo

riparto_regole_fornitore          -- memoria "fai sempre così per questo fornitore"
  id, user_id (account)
  fornitore (normalizzato)
  regola          -- 'equa' | 'percentuali'
  percentuali     -- JSON ristorante_id -> % (solo se regola='percentuali')
  attiva          -- bool
  created_at
```

**Regole di riparto (v1):** `equa` (÷ N sedi) e `percentuali` (decise dal cliente,
es. 70/30 per l'auto). "Per fatturato" ed "escludi sedi" rimandate: le percentuali
coprono già "solo 2 sedi su 3" (50/50 e 0 alla terza). Scelte stabili → nessun
ricalcolo a sorpresa.

**Anti-doppio-conteggio (solo `origine='fattura'`):** una fattura SDI di struttura
ha già i suoi € nel costo *automatico* della sede intestataria. Si marcano quelle
righe come "ripartite" e si **escludono dal costo automatico** di quella sede: il
costo esce dalla porta automatica e rientra distribuito dalla porta manuale.
Totale gruppo invariato. Per `origine='manuale'` il problema non esiste.

**Motore:** RPC SQL che, dato account+mese, somma `quota_importo` per sede e
alimenta l'aggregato di `margini_mensili` — gemella di come `spese_extra` fa oggi.

---

## 5. Creazione di un riparto (due punti d'ingresso)

- **Da una fattura** (commercialista, auto): dal **dettaglio fattura**, pulsante
  **"Ripartisci sul gruppo"** accanto a "Sposta in altra sede". Il cliente sceglie
  `equa` o `percentuali` → conferma. Opzione: **"Fai sempre così per questo
  fornitore"** → crea/aggiorna una `riparto_regole_fornitore`.
- **Voce manuale** (stipendi ufficio, senza fattura): pulsante **"+ Aggiungi costo
  di gruppo"** dentro la finestra Costi di gruppo → descrizione, importo, tipo,
  regola.

**Regola fornitore (propone, non scrive):** quando arriva una nuova fattura di un
fornitore con regola attiva, l'app **propone** il riparto già pronto (badge/coda),
il cliente conferma. Vive a livello account (come i tag di catena). Mai riparto
automatico silenzioso.

---

## 6. DOVE si vede e si gestisce — finestra "Costi di gruppo"

Collocazione: in **`/catena`**, nuova **card-finestra** nella fila delle finestre,
**subito dopo "Spesa per PV"** (stesso pattern di `finestra-spesa-pv.tsx`,
`finestra-margini-coperti.tsx`, `gruppo-tag-section.tsx`). Sola lettura +
aggregazione SQL, coerente con la regola catena. Filtro periodo = **mese
selezionato** (come le altre finestre; niente vista storica separata in v1).

Contenuto: lista dei costi di gruppo del mese, con le quote per sede e la regola:

```
COSTI DI GRUPPO — Giugno
Commercialista      900 €   →  Sede A 450  | Sede B 450   (parti uguali)
Auto aziendale      600 €   →  Sede A 420  | Sede B 180   (70/30)
Stipendi ufficio  2.000 €   →  Sede A 1000 | Sede B 1000  (parti uguali)
```

### Azioni di gestione (dentro la finestra)

| Azione | Cosa succede |
|---|---|
| **Vedi dettaglio / da dove viene** | Se fattura → link al documento; quote per sede; regola; data creazione |
| **Modifica ripartizione** | Cambia regola/percentuali/importo → ricalcola le quote → aggiorna il MOL delle sedi coinvolte |
| **Elimina ripartizione** | Se da fattura → il costo torna intero sulla sede originale (righe rientrano nel costo automatico); se manuale → sparisce |
| **Duplica sul mese dopo** | Ricrea la voce sul mese successivo (per i fissi ricorrenti) |
| **+ Aggiungi costo di gruppo** | Crea una voce manuale senza fattura |
| **Crea/gestisci regola fornitore** | Da un riparto di fattura: "fai sempre così per questo fornitore" |

**Modifica su mesi passati: LIBERA** (nessun blocco sui mesi chiusi). Il MOL del
mese toccato si aggiorna. Scelta consapevole a favore della correggibilità.

---

## 7. Casi limite chiusi

1. **Conflitto sposta ↔ ripartisci:** se una fattura è ripartita, il pulsante
   **"Sposta in altra sede" è disabilitato** (prima si toglie il riparto). Evita
   stati incoerenti (fattura su sede A ma quote su gruppo diverso).
2. **Vista della singola sede:** sul dettaglio della fattura ripartita compare una
   **nota/badge** "Costo ripartito sul gruppo — questa sede: 450€", così chi
   guarda la singola sede (che non usa la catena) capisce perché il MOL non
   riflette i 900€ interi. *(Solo badge nel dettaglio; niente riga extra nel
   calcolo margine in v1.)*
3. **Account a sede singola:** "Ripartisci sul gruppo" e la finestra "Costi di
   gruppo" **appaiono solo con 2+ sedi**. Su sede singola non ha senso dividere →
   funzione nascosta.
4. **Doppio conteggio:** vedi §4 (righe fattura marcate "ripartite" ed escluse dal
   costo automatico della sede intestataria).

---

## 8. Cosa NON copre la v1 (per onestà)

- **Analisi Fatture** (Articoli/Categorie/Fornitori) resta grezza: mostra la
  fattura intera sulla sede intestataria (Proposta 3, rimandata a dopo go-live).
- Regole di riparto avanzate ("per fatturato", "escludi sedi"): rimandate, coperte
  dalle percentuali manuali.
- Vista storica/ricorrenti dedicata: v1 mostra solo il mese selezionato (il
  "duplica sul mese dopo" copre i fissi).

---

## 9. Superficie di lavoro (per stimare quando si implementa)

- **DB:** 3 tabelle nuove + marcatura righe "ripartite" + 1 RPC di aggregazione +
  1 RPC lettura finestra.
- **Worker:** endpoint crea/modifica/elimina/duplica riparto; endpoint regola
  fornitore; gancio proposta in ricezione fattura; guard "blocca sposta se
  ripartita"; esclusione righe ripartite dal costo automatico.
- **Frontend:** dialog "Ripartisci sul gruppo" (dettaglio fattura) + badge nota
  sede; card+finestra "Costi di gruppo" in `/catena` con le azioni; gating 2+ sedi;
  eventuale coda proposte regola fornitore.
- **Test:** anti-doppio-conteggio, equa vs percentuali, elimina→ritorno intero,
  guard sposta, gating sede singola, regola fornitore propone-non-scrive.

---

## 10. Decisioni registrate

- Profondità: **Proposta 2**. ✅
- Regole v1: **equa + percentuali manuali**. ✅
- Creazione: da **fattura** (dettaglio) + **manuale** (finestra). ✅
- Collocazione: **finestra "Costi di gruppo" in `/catena`, dopo "Spesa per PV"**. ✅
- Azioni: modifica, elimina, duplica, dettaglio, +aggiungi, **regola fornitore**. ✅
- Modifica mesi passati: **libera**. ✅
- Storico: **solo mese selezionato**. ✅
- Conflitto sposta: **blocca sposta se ripartita**. ✅
- Vista sede singola: **badge nel dettaglio fattura**. ✅
- Sede singola: **funzione nascosta**. ✅

**Prossimo passo (quando dai OK):** trasformare in piano operativo con migration,
RPC, endpoint e componenti puntuali. Fino ad allora: nulla implementato.
