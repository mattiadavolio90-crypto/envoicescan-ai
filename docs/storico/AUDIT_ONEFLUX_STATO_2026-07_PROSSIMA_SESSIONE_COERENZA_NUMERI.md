# Prompt sessione — verifica di coerenza dei numeri tra le pagine

> Copia il blocco sotto come primo messaggio della nuova sessione.
> Scritto il 27/8/2026. Nasce da un difetto reale trovato *dal cliente*, non
> dall'audit: F&B e Spese Generali non tornavano tra Analisi Fatture, Home e
> Ricavi e Margini (poi sistemato — riparto costi di gruppo LORDO→NETTO,
> commit `26eb14c` + backfill + fix self-healing `f005ca3`).
>
> **Modello: Opus.** WORKFLOW.md §3 — è verifica di correttezza guidata dai
> dati, non trascrizione. Read-only per tutta la sessione: NON modificare nulla.

---

## Cosa devi fare

Una **verifica di quadratura sui numeri reali** tra le pagine dell'app. Prendere
i clienti veri, i mesi veri, e confrontare cifra per cifra lo stesso dato dove
compare in più schermate. Dove non torna, risalire al perché e **fermarti** —
produci un report, non un fix.

Questo NON è quello che ha fatto l'audit §3c. §3c ha *letto il codice* di 11 file
frontend cercando divergenze di tipo/autorità. **Nessuno ha mai preso un cliente
reale e confrontato i numeri a video tra due pagine.** È esattamente il buco da
cui è passato il difetto F&B/Spese Generali.

## Leggi prima (in quest'ordine)

1. `docs/storico/AUDIT_ONEFLUX_STATO_2026-07.md` — §3c e "Chiusura del ciclo".
2. `docs/storico/AUDIT_ONEFLUX_STATO_2026-07_STORICO.md` §25 (i 7 HIGH, il
   "drift di autorità"), §26-§28 (cosa è già stato corretto).
3. CLAUDE.md — regole di dominio #1 (Da Classificare fuori dai margini), #2
   (NOTE E DICITURE solo se totale_riga==0), #5 (soft delete).

## Il pattern già noto: "drift di autorità"

Su 4 dei 7 HIGH di §25 la causa era la stessa: **il client ri-calcola in locale
un numero che il worker gli ha già mandato giusto**, oppure chiama l'endpoint
grezzo invece di quello che applica le regole di dominio. La prova sta in
`services/routers/ricavi.py` (cerca il commento sull'override mensile che ha
"precedenza sui giornalieri") — regola implementata e commentata in UN punto,
mai propagata agli altri consumatori. **Cerca altre occorrenze di questo.**

Due fatti strutturali che lo spiegano (misurati in §25):
- `grep -ril openapi apps/web` → **0**: nessun codegen dai tipi. La CI protegge
  Python↔schema, niente protegge schema↔TypeScript. Tutti i tipi TS sono a mano.
- **111 `await res.json()` nei .tsx, solo 16 tipizzati**: ~95 risposte entrano in
  React come `any`. Un campo rinominato lato Pydantic sparisce senza errore.

## Clienti e sedi reali (misurato 27/8/2026)

| ristorante_id | sede | email | n_fatture | mesi | note |
|---|---|---|---|---|---|
| `fd7ac484-b562-498d-a6d1-00c4c6fd09dd` | LAND DEI SAPORI SRL | ghyl.888@gmail.com | 12956 | 2026-01→07 | 2 fatture ripartite su gruppo |
| `cc016821-e749-4323-9568-3781c69384d3` | SUSHILAND VILLA GUARDIA | ghyl.888@gmail.com | 6411 | 03→07 | catena SUSHILAND (stesso user) |
| `5444e918-8616-464c-a109-5d8aba226805` | SUSHILAND SAN GIULIANO | ghyl.888@gmail.com | 5620 | 03→06 | |
| `0dca4d1f-0caa-419a-b869-25bd98f424e1` | SUSHILAND MARIANO COMENSE | ghyl.888@gmail.com | 4592 | 03→06 | |
| `86300227-53c3-4193-9b45-761b3654e889` | TIME CAFE | davide.pizzata.78@gmail.com | 3888 | 01→07 | `blocco_mesi_precedenti=true` (switch morto, §25 HIGH 7) |
| `bdda08d1-9490-486c-adfb-dd05cbddc25c` | OFFSIDE SPORTS PUB | offsidesp@gmail.com | 1978 | 01→**08** | catena OFFSIDE, riparto costi gruppo |
| `dcf1996e-f430-4549-8505-902b169f6bab` | OVERTIME | offsidesp@gmail.com | 1169 | 01→08 | catena OFFSIDE — 6 mesi solo modalità mensile, 0 giornalieri |
| `f16aebe5-735b-4d1b-a168-81af1547db03` | CASATI 14 | fra.diclemente@gmail.com | 1264 | 03→08 | |
| `f7bba05f-90a8-4f12-94ed-4d8a08a0bbae` | Costi comuni di gruppo | offsidesp@gmail.com | 804 | 01→08 | **sede tecnica** OFFSIDE — tutte le 804 fatture ripartite |

Project Supabase: `vthikmfpywilukizputn`. Usa `mcp__claude_ai_Supabase__execute_sql`
(read-only). `service_role_key`, `auth.uid()` sempre NULL.

**Priorità di verifica** (per esposizione al difetto già visto):
1. **OFFSIDE SPORTS PUB + OVERTIME** — il caso da cui è nato tutto. Riparto costi
   di gruppo attivo, agosto incluso, e OVERTIME ha 6 mesi in sola modalità
   mensile (nessun giornaliero): è la configurazione che ha innescato 2 dei 7 HIGH.
2. **La catena OFFSIDE** — pagina `catena/`, confronto sede-singola vs vista di
   gruppo. Qui c'è il MEDIUM ancora aperto (vedi sotto).
3. **La catena SUSHILAND** (3 sedi, stesso user_id) — pagina catena, tag di gruppo.
4. **LAND DEI SAPORI** — volume più alto, 2 fatture ripartite su gruppo.
5. **TIME CAFE** — ha lo switch morto `blocco_mesi_precedenti` acceso.

## Le pagine e da dove prendono i numeri (mappato 27/8)

| Pagina | File | Endpoint principali |
|---|---|---|
| **Home / Dashboard** | `apps/web/src/app/(app)/dashboard/` | `/api/home/kpi`, `/api/home/briefing` |
| **Analisi Fatture** | `apps/web/src/app/(app)/analisi-fatture/` | `/api/fatture/righe-articolo`, `/api/fatture/trend`, `/api/fatture/categoria-batch` |
| **Ricavi e Margini** | `apps/web/src/app/(app)/margini/` | `/api/margini/analisi`, `/api/margini/analisi-avanzata`, `/api/margini/cella`, `/api/margini/fatturato-centri[-giorni]`, `/api/ricavi/giornalieri`, `/api/ricavi/modalita`, `/api/ricavi/coperti-analisi` |
| **Catena** | `apps/web/src/app/(app)/catena/` | `/api/gruppo/costi-comuni`, `/api/gruppo/margini-coperti`, `/api/gruppo/spesa-pivot`, `/api/gruppo/segnali`, `/api/gruppo/tag*` |
| **Prezzi** | `apps/web/src/app/(app)/prezzi/` | (variazioni, score) |
| **Analisi e Tag** | `apps/web/src/app/(app)/analisi-e-tag/` | `/api/gruppo/tag*` e tag per-sede |

Router Python: `services/routers/{margini,ricavi,fatture,gruppo,riparto}.py`.
La logica MOL/1° Margine sta in `margini.py` (cerca `primo_margine`, `mol`,
`_aggrega_mensili_margini`). Le RPC DB `costi_automatici_mensili[_gruppo]` fanno
la somma dei costi per categoria.

## I confronti da fare, esplicitamente

Per ogni sede prioritaria, per ogni mese con dati, confronta questi valori
**letti dal DB come fonte di verità** contro **cosa restituisce ogni endpoint**:

### A. Fatturato / ricavi netti del mese
- Home KPI vs Ricavi e Margini (tab Calcolo) vs Ricavi e Margini (tab Analisi
  per centro) vs `/api/ricavi/giornalieri` sommato.
- **Trappola nota (§25 HIGH 1-2)**: `analisi-tab.tsx` e `calcolo-tab.tsx`
  leggevano il netto da `/api/ricavi/giornalieri` (grezzo, ignora l'override
  `ricavi_modalita_mensile`). Corretto il 25/8 — **verifica che il fix sia
  consumato** su OVERTIME (6 mesi mensile puro).
- Modulo differenza strutturale nota: `data_competenza` vs `data_documento`
  (`data_competenza` è NULL sul 99,3% delle righe → fallback a `data_documento`;
  229 righe cadono in un mese diverso).

### B. Costi F&B del mese (il difetto appena chiuso)
- Home vs Analisi Fatture (somma righe categoria F&B) vs Ricavi e Margini
  (`costi_fb` nel MOL) vs, per OFFSIDE, la quota di riparto dalla sede tecnica.
- **Regola #1**: le righe `Da Classificare` sono ESCLUSE dai margini ma VISIBILI
  in Analisi Fatture → i due totali divergono *legittimamente* di quella quota.
  Quantificala, non darla per rumore.
- **Riparto costi gruppo**: per OFFSIDE le fatture strutturali stanno sulla sede
  tecnica `f7bba05f...` e rientrano via `margini_mensili.quote_riparto_fb` /
  `quote_riparto_spese`. Verifica che la quota che rientra = quota che esce dalla
  sede tecnica, mese per mese, e che sia NETTA (post-fix 26eb14c).

### C. Spese Generali del mese
- Stessa triangolazione di B. La categoria "SERVIZI E CONSULENZE" e le spese
  extra manuali (`/api/margini/costo-spese-extra`) entrano qui.
- **Trappola nota (§28)**: "8 descrizioni a cavallo F&B/spese-generali" per
  (sede, descrizione) — verifica che una descrizione non venga contata in
  entrambe le categorie in pagine diverse.

### D. 1° Margine e MOL
- Home vs Ricavi e Margini. Formula: `primo_margine = fatt_netto - costi_fb`;
  `mol = primo_margine - costi_spese - costi_personale`.
- **Trappola nota (§25)**: le soglie colore (rosso/arancio/giallo/verde) per MOL
  **divergono tra TypeScript e Python su tutta la banda 5-20%**. `lib/margini.ts`
  è dead code (0 consumer) ma controlla che le soglie *vive* nel client
  (`kpi-bar.tsx`, `calcolo-tab.tsx`) coincidano con `margini.py:770-800`.

### E. Catena vs somma delle sedi
- La vista catena di un totale (costi comuni, margini-coperti, spesa-pivot) deve
  = somma delle singole sedi, per lo stesso periodo.
- **MEDIUM ANCORA APERTO (§25, §3c)**: divergenza sede-singola↔catena sui tag di
  gruppo. Misurata: **402.182,19 € vs 402.418,42 € = 236,23 €** di note di
  credito non scalate sul percorso catena. Esiste `gruppo_tags` id=3 "SALMONE"
  (5 prodotti, tutti KG) su SUSHILAND e "SALMONE" analogo su OFFSIDE. Richiede
  una migration su 6 RPC `gruppo_tag_*` → **NON fixare, conferma il numero e
  riportalo**.

### F. Prezzi / alert prezzi
- Il prezzo medio di un prodotto/tag in pagina Prezzi vs l'alert prezzi in Home
  (`price_impact_service`) vs il KPI in Analisi e Tag.
- **Trappola nota (§3b, 24/8)**: `_compute_kpi` scommava KG+LT+PZ. Corretto, ma
  `prezzo_medio_tag` **non è consumato dal client** (§25): arriva in
  `fornitori.aggregati` e viene scartato — colonna "Vs media" senza la media.

## Metodo (dal ciclo di audit — non derogare)

- **Read-only.** Nessuna modifica a codice, DB, migration. Produci un report.
- **Riverifica ogni numero sul DB.** Nel ciclo è successo 8 volte che una
  severità cadesse a una query. Non fidarti di quello che dice una pagina:
  ricostruisci il valore atteso da SQL e confrontalo.
- Per il frontend non ci sono test: verifica leggendo il codice del componente
  e, se serve, eseguendo il percorso mentalmente con dati reali.
- Distingui **divergenza legittima** (documentata: `data_competenza` vs
  `data_documento`, `Da Classificare` escluse dai margini, costo personale nel
  MOL, competenza vs cassa) da **bug** (stesso dato, stessa definizione, due
  numeri). Quantifica sempre la prima, non liquidarla come rumore.
- Se trovi un cambio di branch/commit non tuo → qualcun altro sta lavorando sul
  repo, fermati e chiedi.

## Output atteso

Un documento `scratchpad/coerenza_numeri_report.md` con, per ogni sede × mese ×
metrica (A-F):
- valore atteso (da SQL, con la query)
- valore di ogni pagina/endpoint che lo mostra
- delta, e se è **legittimo** (con la causa strutturale) o **bug** (con l'ipotesi
  di causa nel codice — file:riga)
- una tabella riepilogo "tutto quadra / quadra modulo X / non quadra" per sede

Poi **fermati e riporta a Mattia.** La remediation è una decisione sua, sessione
separata, come per tutti i fix del ciclo di audit.

## Fuori scope

- Qualunque fix (codice, DB, migration).
- Il MEDIUM catena-tag (§25): conferma il numero, non correggerlo.
- Edge Function `invoicetronic-webhook` (gestita in altra sessione, 27/8).
- Riscrittura del parsing / dell'ingestione: già chiusa (`f005ca3`).
- Audit di stile / accessibilità: già fatto dalla dimensione 6.
