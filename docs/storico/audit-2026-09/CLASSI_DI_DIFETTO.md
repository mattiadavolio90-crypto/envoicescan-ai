# Catalogo delle classi di difetto — sweep sistematico (14/09/2026)

> **A cosa serve.** Seconda lente trasversale (L1): ogni classe di difetto già
> pagata nei tre cicli viene cercata **ovunque** nel codice con un rilevatore
> (AST Python / grep TS), non incontrata per caso. Per ogni classe: quanti
> candidati, quanti reali dopo il triage, quanti confermati con misura, i fix
> fatti e il presidio che impedisce la ricomparsa. Ri-eseguire il rilevatore,
> non rileggere questo file.

**Metodo.** Rilevatori in locale (`scratchpad` della sessione: AST su
`services/ worker/ utils/ config/` — 10 file hanno il BOM, leggere con
`utf-8-sig` — e grep su `apps/web/src`), candidati con contesto passati a
**un** agente per classe (8 agenti, 707 candidati, 866k token), refutazione
con misura sul DB live per il cap PostgREST (1 agente; gli altri 5 refutatori
sono caduti per limite di sessione: le loro classi sono **triage, non
refutazione**, e lo dice la colonna). Fix e presidi a mano, un mutante per fix.

## Il quadro

| Classe | Candidati | Reali (triage) | Confermati con misura | Fix 14/09 | Presidio |
|---|---|---|---|---|---|
| Cap PostgREST 1000 righe (`.select().execute()` senza `range`/`fetch_all`) | 159 | 7 | **2 su 16 misurati** (14 refutati con la cifra) | export GDPR `account.py` (4 clienti su 6 troncati: 29.911 fatture consegnate come 1000); mappa fornitori `scadenziario.py` (LAND a 938/1000, +214 in 30 gg) | `test_account_export_oltre_il_cap.py`, `test_scadenziario_fornitori_oltre_il_cap.py` (fake che cappa a 1000 senza `range`) |
| Paginazione senza ORDER BY (`fetch_all`/`.range` senza `.order`) | 35 | 16 (1 alta, 9 medie) | non refutati (agente caduto); 28 chiamanti su 35 senza ordine | **chokepoint**: `fetch_all` aggiunge `.order("id")` se manca, salta le RPC (`articoli_da_fatture` non ha `id`), i fake e i `MagicMock` (parametri non `Mapping`); `.order("id")` nei 3 loop `.range` a mano (`admin.py` 764/782, `fatture.py` 801) e nello Step 1 dello scadenziario | `test_fetch_all_ordine_totale_chokepoint.py` (mutanti «mai» e «anche le RPC») |
| `except` che produce il valore «tutto ok» | 204 → 125 filtrati | 24 (1 alta, 9 medie) | letto il chiamante per l'alta (io) | `_load_mensile_overrides` ora **logga** l'errore (prima: `{}` muto letto da 20+ consumatori come «nessun mese mensile» → fatturato 0, MOL −100%) | `test_load_mensile_overrides_non_tace.py` |
| Orologio senza fuso / `new Date()` / `startsWith` su path | 70 | 9 (5 medie) | letto (io) | `documenti_service.py` 646/958: `date.today()` → `_oggi_rome()` (esisteva nello stesso file) | `test_stato_scadenza_giorno_di_roma.py` |
| Costante di dominio duplicata (IVA, soglie, mesi) | 65 | 40 (5 medie, 35 basse) | — | `margini.py:259` `/1.10 /1.22` → `IVA_DIVISORE_10/22` (mutante equivalente: nessun presidio possibile) | — |
| `null`/errore → «vuoto ma valido» nel frontend (R10) | 143 | 40 (7 medie) | — | **nessuno** (`.tsx` non mutabile; elenco sotto) | — |
| `or` su default ≠ 0 / `.neq` NULL-unsafe | 35 | 0 | — | — | — |
| Scrittura senza filtro tenant (`update/delete` senza `user_id`/`ristorante_id`) | 75 | 0 | — | 1 residuo: `dismiss_inbox_notification` senza `user_id`, **zero chiamanti** (test che dichiara un isolamento che non c'è) | — |

## Cosa resta aperto, per classe (triage non refutato: da verificare leggendo il chiamante prima di toccare)

- **except→ok, medie**: `gruppo.py:168` (stesso `{}` muto del wrapper); `fastapi_worker.py:8770` (`_righe_quote_gruppo` → `[]`: quote ripartite sparite dai totali); `ai_cost_service.py:84` (quota AI = 0 su errore → nessun tetto; fail-closed spegnerebbe la classificazione su un blip: **decisione di prodotto**); `fastapi_worker.py:1966` (`[]` sedi → upload scartato con motivo falso); `session_service.py:256` (reset password risponde ok con 0 sessioni revocate); `notification_inbox_service.py:209` (`ok:True, inserted:0`); `documenti_service.py:346` e `db_service.py:2165` (**`[]` su errore cachato** 120 s / 300 s: `get_or_set` memorizza tutto tranne `None` — chokepoint candidato); `admin.py:2291` (badge admin a 0 su errore).
- **paginazione, medie**: `documenti_service.py:736` (ora coperto dal chokepoint), `fatture.py` 835/927/944, `fastapi_worker.py` 5402/6100/7672: tutti passano da `fetch_all` → coperti dal chokepoint. L'instabilità **non si è riprodotta** il 14/09 (10 letture su 12.956 e 2.609 righe, 0 mancanti): l'ordine è garanzia, non riparazione di un guasto visibile oggi.
- **frontend R10, medie**: `coda-da-assegnare.tsx:158` (worker giù → coda vuota, proprio le 20 di OFFSIDE), `carica-ricavi-dialog.tsx` 137/163 (righe vuote da compilare, modalità mensile persa), `personale-tab.tsx:1417` (`r.json()` senza `res.ok`), `admin/page.tsx` 34/53 (badge a 0 su errore). Stesso pattern di `lib/esito-caricamento.ts`: da applicare.
- **orologio, medie**: `margini/periodi.ts:29` e `analisi-fatture/periodi.ts:22` chiamate da Server Component con `new Date()` UTC (2 ore/giorno il mese sbaglia a cavallo del 1°); `inventario-tab.tsx:27` `todayISO()` UTC come chiave del dato.
- **duplicati, medie**: benchmark testuali del prompt chat (`fastapi_worker.py` 3774/3897) copiati a mano da `KPI_SOGLIE`.
- **cap, basse (refutate ma «al ritmo attuale»)**: `admin.py:2457` (654/1000 su 365 gg), `workspace.py:2276` (turni da regole: >1000 con 11+ dipendenti → duplicati), `ClassificaBody.ids` senza `max_length` (gruppi max 115 oggi). `.limit(10000)` in `anomaly_radar_service.py` è clampato a 1000 da `max_rows`: promette 10.000, ne consegna 1.000 (oggi bastano: max 115 per P.IVA).

## Rilevatori: cosa hanno preso di troppo (per la prossima corsa)

cap: tabelle piccole per natura (users, ristoranti, categorie, margini_mensili…), `count=exact` senza `.data`, `.in_` su chunk < 1000, `.eq` su chiave unica (143 benigni su 159). except→ok: `return {"success": False}` è l'**opposto** della classe (~30), parser stretti `(TypeError, ValueError)`, stub d'import; **mancano** le forme `except: pass` con default «ok» inizializzato prima del `try`. null frontend: `?? ""` su className/title, lookup su mappe locali (70+). tenant: `users` self, tabelle globali, worker su righe reclamate.
