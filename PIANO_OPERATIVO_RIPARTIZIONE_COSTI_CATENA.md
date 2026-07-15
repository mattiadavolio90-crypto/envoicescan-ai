# Piano operativo — Ripartizione costi di gruppo sulle catene

> Stato: **PIANO OPERATIVO**, nessun codice scritto. Data: 14/7/2026 — Owner: Mattia.
> Traduce in migration/RPC/endpoint/componenti la decisione già presa in
> `PIANO_RIPARTIZIONE_COSTI_CATENA.md` (1/7, Proposta 2), **estesa** con l'anello
> d'ingresso che quel documento non copriva (fatture di struttura respinte
> all'upload). Caso reale che lo motiva: OFFSIDE SRL, ~240/383 fatture 1° sem 2026
> intestate a sede legale (Fulvio Testi vecchia, Montalbino nuova), non ai locali.
> Da rivedere e approvare PRIMA di implementare.

---

## 0. Il buco che questo piano chiude (nuovo rispetto al 1/7)

Il piano del 1/7 assume la fattura **già dentro l'app, su una sede**. Ma le
fatture di struttura di OFFSIDE hanno P.IVA corretta e indirizzo di **nessun
locale** → oggi l'upload manuale le **RESPINGE** come `SEDE_AMBIGUA`
([fastapi_worker.py:1892-1904](services/fastapi_worker.py#L1892-L1904)), via
`decidi_destinazione_upload` → `decidi_sede` che ritorna `ambiguo` quando nessuna
sede supera `MIN_SCORE=0.40`/`MIN_GAP=0.20`
([multisede_routing.py:135-143](services/multisede_routing.py#L135-L143)).
Lo stesso vale per il canale SDI (Edge Function → `fatture_queue`).

**Non entrano → non si possono ripartire.** Prima serve farle entrare.

### Decisione sull'ingresso (scelgo io, come richiesto)

**Riuso la coda `da_assegnare` già esistente, NON invento indirizzi amministrativi.**

Motivi, ancorati al codice:
- La coda `da_assegnare` su `fatture_queue` esiste già, con constraint, indice
  parziale, UI admin ("Flusso dati") e RPC di assegnazione
  ([20260611140000_multi_sede_routing.sql:126-154](supabase/migrations/20260611140000_multi_sede_routing.sql#L126-L154),
  [assegna-sede route](apps/web/src/app/api/admin/fatture-queue/assegna-sede/route.ts)).
  È esattamente il pattern "fattura che qualcuno deve smistare a mano".
- Registrare Fulvio Testi/Montalbino come "sedi amministrative" creerebbe **entità
  senza incassi** — l'opzione che Mattia ha già **bocciato** ("confusionario perché
  non ha incassi"). Falserebbe `num_pv`, ranking, salute gruppo
  ([sintesi-catena.tsx:440-514](apps/web/src/app/(app)/catena/sintesi-catena.tsx#L440-L514)).
- Gli indirizzi legali sono **due e cambiano** (vecchia/nuova sede): inseguirli nel
  routing è fragile. La coda invece è agnostica all'indirizzo: intercetta
  *qualsiasi* ambiguo.

**Comportamento nuovo:** oggi `mode == 'ambiguo'` sull'upload manuale scarta. Con
questo piano l'ambiguo (P.IVA nota, sede non decidibile) **non scarta più**: crea
la fattura in uno stato "da smistare" e la mette nella coda. Da lì il cliente/admin
sceglie **una** delle tre azioni: (a) assegna a un locale, (b) **ripartisci sul
gruppo**, (c) tieni su una sede etichettandola comune. La (b) è il ponte verso il
resto del piano del 1/7.

> Distinzione netta da tenere ferma: `piva_estranea` (P.IVA di **nessuna** sede del
> cliente) **continua a scartare** — è la guardia anti-fattura-sbagliata, non si
> tocca. Cambia solo `ambiguo` (P.IVA giusta, sede incerta).

---

## 1. Modello dati (migration)

Tutte le migration in `supabase/migrations/` con timestamp `AAAAMMGGHHMMSS_*.sql`
(la cartella `migrations/` numerata è congelata — CLAUDE.md).

### 1a. Ingresso — stato "da smistare" sull'upload manuale

Riuso `fatture_queue` invece di una tabella nuova: l'upload oggi salva diretto in
`fatture` senza passare dalla coda ([multisede_routing.py:11-12](services/multisede_routing.py#L11-L12)).
Per far confluire anche il manuale nella coda serve **poter mettere in
`fatture_queue` una riga con `source_origin='manual'`** e il payload già decodificato.

- Verificare che `fatture_queue` accetti `da_assegnare` con `ristorante_id NULL`
  (constraint `chk_fatture_queue_tenant_consistency` lo ammette già —
  [20260611140000:139-149](supabase/migrations/20260611140000_multi_sede_routing.sql#L139-L149)).
- Aggiungere colonna `source_origin TEXT DEFAULT 'invoicetronic'` a `fatture_queue`
  se non c'è, per distinguere gli ambigui manuali da quelli SDI (serve alla UI).
- Nessuna fattura viene creata in `fatture` finché non è assegnata: l'ambiguo vive
  solo in coda. Così **il cliente NON vede numeri sbagliati** su nessuna sede nel
  frattempo (risolve il rischio "margini gonfiati durante lo smistamento").

### 1b. Ripartizione — 3 tabelle nuove (dal §4 del piano 1/7, invariate)

```
riparto_costi_catena
  id, user_id (account), origine ('fattura'|'manuale'),
  file_origine (NULL se manuale), descrizione, importo_totale,
  tipo ('generale'|'fb'), anno, mese, regola ('equa'|'percentuali'),
  created_at, updated_at

riparto_costi_catena_quote
  riparto_id (FK), ristorante_id, quota_perc, quota_importo
  UNIQUE (riparto_id, ristorante_id)

riparto_regole_fornitore
  id, user_id (account), fornitore (normalizzato),
  regola ('equa'|'percentuali'), percentuali (JSONB rid->%),
  attiva (bool), created_at
```

### 1c. Anti-doppio-conteggio — marcatura righe ripartite

Serve escludere dal costo automatico della sede intestataria le righe di una
fattura ripartita. Il costo automatico filtra oggi
`.eq('ristorante_id').neq('categoria','Da Classificare')`
([margine_service.py:84-99](services/margine_service.py#L84-L99)) e la RPC
`costi_automatici_mensili` / `dashboard_stats_aggregata`.

- Aggiungere `ripartita_su_gruppo BOOLEAN DEFAULT FALSE` su `fatture` (livello riga,
  come `needs_review`), indice parziale `WHERE ripartita_su_gruppo = true`.
- Il costo automatico dovrà aggiungere `.neq('ripartita_su_gruppo', true)` / clausola
  `AND NOT ripartita_su_gruppo` nella CTE. **Punti da toccare (3):**
  1. query pandas fallback [margine_service.py:84-99](services/margine_service.py#L84-L99) e ~230-239
  2. RPC `costi_automatici_mensili` (SQL)
  3. RPC `dashboard_stats_aggregata` CTE `base`
     ([20260620020000:41-52](supabase/migrations/20260620020000_rpc_dashboard_stats_aggregata.sql#L41-L52))

### 1d. Motore aggregazione (dal §4 piano 1/7)

RPC `riparto_quote_mensili(p_user_id, p_anno, p_mese)` → somma `quota_importo` per
`ristorante_id`, separando `tipo='fb'` (→ `altri_costi_fb`) da `'generale'`
(→ `altri_costi_spese`). Alimenta `margini_mensili` **come già fa `spese_extra`** —
il motore MOL non cambia (principio non negoziabile §2 piano 1/7).

---

## 2. Worker (endpoint FastAPI, in `services/routers/`)

Nel router fatture/gruppo esistenti, non un god-file nuovo.

| Endpoint | Cosa fa |
|---|---|
| `POST /api/fatture/ambigue/importa` | Accetta un ambiguo in coda: crea la fattura in `fatture` sulla sede scelta (riusa `assegna_fattura_a_sede`) **oppure** avvia la ripartizione |
| `POST /api/riparto/crea` | Crea `riparto_costi_catena` + `_quote` da una fattura (`equa`/`percentuali`); marca righe `ripartita_su_gruppo=true` |
| `PATCH /api/riparto/{id}` | Modifica regola/percentuali/importo → ricalcola quote |
| `DELETE /api/riparto/{id}` | Se da fattura → smarca righe (costo torna intero sulla sede); se manuale → elimina |
| `POST /api/riparto/{id}/duplica` | Ricrea la voce sul mese successivo |
| `POST /api/riparto/manuale` | Voce senza fattura (stipendi ufficio) |
| `GET /api/gruppo/costi-comuni?anno&mese` | Lista per la finestra catena (aggregazione SQL, sola lettura) |
| `POST /api/riparto/regola-fornitore` | Crea/aggiorna regola "fai sempre così" |

**Guard obbligatori (dal §7 piano 1/7):**
- "Sposta in altra sede" disabilitato se la fattura è ripartita
  ([sposta-sede in fatture.py:1022-1084](services/routers/fatture.py#L1022-L1084) → aggiungere check).
- Gating 2+ sedi su tutti gli endpoint riparto.
- Regola fornitore **propone, non scrive** (filosofia ONEFLUX): alla ricezione di una
  fattura di un fornitore con regola attiva, mette una **proposta** in coda, non
  applica in automatico.

**Invalidazioni (buco emerso nell'audit di oggi):** ogni scrittura riparto deve
- invalidare la cache righe fatture (già fa `_invalidate_fatture_rows_cache`),
- **`DELETE daily_briefing_state`** delle sedi coinvolte + bump `_BRIEFING_CODE_VERSION`
  se tocca la logica (oggi lo spostamento NON lo fa — briefing resta stantìo).

---

## 3. Frontend (`apps/web/src/app`)

### 3a. Coda ambigui (ingresso)
Estendere la UI admin **"Flusso dati"**
([flusso-dati-client.tsx](apps/web/src/app/(app)/admin/flusso-dati/flusso-dati-client.tsx)):
per un ambiguo, oltre a "Scegli sede", il bottone **"Ripartisci sul gruppo"**.
Stesso pattern del dialog `NativeSelect` già presente.

### 3b. Dettaglio fattura
Pulsante **"Ripartisci sul gruppo"** accanto a "Sposta in altra sede" (Scadenziario).
Dialog: `equa` | `percentuali` (slider/campi per sede, somma=100%) + checkbox
"Fai sempre così per questo fornitore". Badge sul dettaglio della fattura ripartita:
*"Costo ripartito sul gruppo — questa sede: 450€"* (§7.2 piano 1/7).

### 3c. Finestra "Costi di gruppo" in `/catena`
Nuova `ConfrontoCard` + finestra lazy dopo "Spesa per PV", stesso pattern di
[sintesi-catena.tsx:468-520](apps/web/src/app/(app)/catena/sintesi-catena.tsx#L468-L520).
Contenuto: lista costi del mese con quote per sede e regola; azioni: dettaglio,
modifica, elimina, duplica, +aggiungi, gestisci regola fornitore. Filtro = mese
selezionato. Gating `num_pv >= 2` (già `redirect` se `<2` in [page.tsx:32-48](apps/web/src/app/(app)/catena/page.tsx#L32-L48)).

Badge contatore ambigui "da smistare" a livello gruppo, per rendere **riconoscibili**
le fatture che il cliente deve gestire (requisito esplicito di Mattia).

---

## 4. Default e granularità (decido io, come richiesto)

- **Default all'ingresso:** l'ambiguo NON entra in nessun margine finché non è
  gestito (vive in coda, §1a). Niente "50/50 automatico silenzioso": violerebbe
  "regole/AI propongono, il cliente decide". Ma per non lasciare il costo fuori dai
  conti, la coda è **visibile e sollecitante** (badge contatore).
- **Granularità:** per singola fattura, editabile (`equa`/`percentuali`), + memoria
  opzionale per fornitore (`riparto_regole_fornitore`) che **propone** il default la
  volta dopo. Copre "commercialista sempre 50/50" senza rifarlo ogni mese, e
  "riparazione idraulica 100% su un locale" come override.

---

## 5. Test (pytest + Deno)

- Anti-doppio-conteggio: fattura ripartita esclusa dal costo automatico, totale
  gruppo invariato.
- `equa` vs `percentuali`, somma quote = importo.
- `DELETE` riparto → righe smarcate, costo torna intero.
- Guard "sposta bloccato se ripartita".
- Gating sede singola (funzione nascosta).
- Regola fornitore **propone, non scrive**.
- **Nuovo:** ambiguo upload manuale → coda `da_assegnare` (non più scartato);
  `piva_estranea` → **ancora** scartata (guardia intatta).
- Allineamento 3 implementazioni routing (Python/TS/SQL) non regredito.

---

## 6. Ordine di implementazione consigliato

1. **Ingresso** (§1a + endpoint importa + UI Flusso dati): sblocca il caricamento
   OFFSIDE senza perdere fatture. Da solo già utile: le ambigue entrano in coda.
2. **Riparto core** (§1b/1c/1d + endpoint crea/modifica/elimina + esclusione costo
   automatico): il MOL diventa onesto.
3. **Finestra catena** (§3c) + badge + regola fornitore: visibilità e gestione.
4. Test a ogni fase.

Fase 1 è indipendente e a basso rischio: si può fare e verificare su OFFSIDE prima
di costruire il riparto. Le altre seguono il piano del 1/7 già approvato.

---

## 7. Cosa NON copre (invariato dal 1/7)

Analisi Fatture resta grezza (Proposta 3 rimandata); regole avanzate ("per
fatturato", "escludi sedi") rimandate; vista storica dedicata rimandata (solo mese
selezionato, "duplica" copre i ricorrenti).
