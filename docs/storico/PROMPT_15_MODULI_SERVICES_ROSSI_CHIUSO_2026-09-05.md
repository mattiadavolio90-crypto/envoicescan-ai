# Prompt sessione — i 15 moduli `services/` ancora mai guardati

> **Modello**: **Opus**, `ultrathink` in apertura — `documenti_service` regge lo
> scadenziario (4,4 M€ di scadenze) e `tag_suggestion_service` tocca la
> categorizzazione, cioè la regola di dominio #1.
> **Sforzo**: alto. È una dimensione di audit, non un fix.
> **Voce di roadmap**: §0 di `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-09.md`.

---

## Perché questa sessione

È **l'ultima zona rossa del backend**. Il 05/09 sono stati chiusi `utils/` e i 4
moduli del "nucleo" (riparto, foodcost, radar, price_impact): restano **15
moduli `services/`, 5.147 righe**, mai letti da nessuna passata.

**Perimetro ri-misurato il 05/09** — la colonna chiude, verificata addendo per
addendo (`ai_cost_service` è **282**, non 283: una review l'aveva dato per 283):

| Modulo | Righe | Test dedicati |
|---|---:|---|
| `documenti_service.py` | 1.096 | 2 file |
| `tag_suggestion_service.py` | 1.087 | 1 file |
| `tag_analytics_service.py` | 488 | 1 |
| `notification_inbox_service.py` | 352 | 1 (669 righe) |
| `personale_export_service.py` | 291 | **0** |
| `ai_cost_service.py` | 282 | 1 |
| `worker_client.py` | 270 | **0** |
| `__init__.py` | 259 | **0** |
| `multisede_routing.py` | 223 | 1 |
| `session_service.py` | 219 | 1 |
| `_streamlit_shim.py` | 137 | **0** |
| `upload_policy.py` | 134 | 2 |
| `consumi_service.py` | 134 | 1 |
| `worker_metrics.py` | 106 | 1 |
| `telegram_service.py` | 69 | 1 |
| **Totale** | **5.147** | |

⚠️ **Ri-misura in apertura**: `find services -name '*.py' | xargs wc -l`. In
questo ciclo **undici** cifre ereditate da documenti non hanno retto.

## Misura a DB fatta il 05/09 (ri-falla: cambia in giorni)

Progetto `vthikmfpywilukizputn`. Tutte le aree sono **vive**, nessuna è vuota —
diversamente dal food cost, che il prompt precedente metteva in primo piano e
aveva 5 ricette di 1 utente:

- `fatture_documenti` **3.542** → `documenti_service`
- `ai_usage_events` **550** → `ai_cost_service`
- `sessioni` **383** → `session_service`
- `custom_tag_suggestion_items` **330**, `custom_tag_prodotti` 170,
  `custom_tag_suggestions` 62, `custom_tags` 16 → `tag_suggestion` + `tag_analytics`
- `notification_inbox` **70** → `notification_inbox_service`

## Da dove partire

1. **`documenti_service.py` (1.096)** — regge lo scadenziario. Il 3/09 è già
   emerso che gli avvisi erano **muti da giugno** e che `workerGet` a `null`
   diventava lista vuota su **4,4 M€ di scadenze**. È il modulo con più soldi
   dietro.
2. **`tag_suggestion_service.py` (1.087)** — tocca la categorizzazione (regola
   #1). 330 item suggeriti in produzione.
3. **`services/__init__.py` (259)** — **non è un `__init__` vuoto**: contiene la
   risoluzione delle credenziali e la `service_role_key`. CLAUDE.md #3 dice di
   non toccarlo senza capire l'auth flow — e nessuno l'ha mai letto. Zero test.
4. I tre **senza alcun test**: `personale_export_service` (291), `worker_client`
   (270), `_streamlit_shim` (137).

## Cosa cercare (dove il ciclo ha trovato i difetti veri)

- **Funzioni senza chiamanti runtime.** Il 05/09 sono emersi 2 moduli interi
  morti in `utils/` (250 righe) più `patch_streamlit_width_api`. Il metodo:
  grep dei chiamanti in `.py`/`.ts`/`.tsx` **escludendo `tests/`**, e per i
  moduli sospetti `python -c "import il.modulo"` fuori da pytest — un test verde
  può girare solo grazie allo shim del conftest.
- **Query non paginate.** `.execute()` diretto senza `.range()`: PostgREST
  tronca a 1000 **senza errore né log**. Usare `fetch_all` di
  `utils/supabase_paging` (che ora ha un presidio, 3/3 mutanti). Nel riparto il
  cap era al 24% e cresceva.
- **Soft delete**: ogni query su `fatture`/`prodotti` deve filtrare
  `deleted_at IS NULL` — meglio `filter_active()` di `services.db_service`.
- **Fallback che restituiscono un valore plausibile**: `[]`, `0`, `{}` su
  errore. Un totale più basso ma valido è peggio di un errore, perché nessuno
  se ne accorge.
- **Basi delle percentuali**: prima di dire che una percentuale non torna,
  guarda su quale chiave è definita (schema + migration). Somme multiple di 100
  di solito significano che stai aggregando fra gruppi.

## Rilievi già aperti dal 05/09, da valutare qui

Trovati leggendo i 4 moduli del nucleo, **non corretti** perché fuori perimetro:

- **`price_impact`: `impatto_mese` su due scale diverse.** Prodotti = quantità
  media × frequenza con cap 6/mese; tag = totale periodo × 30/45. Poi vengono
  **ordinati insieme e tagliati a 3**. È un rilievo di prodotto.
- **Asimmetria `Da Classificare` fra i due consumatori di
  `righe_ripartite_proiettate`**: `fastapi_worker.py:8330` filtra citando la
  regola #1, `:8215` no. Misurato: **70 quote, 1.270,21 €** → due tab possono
  dare numeri diversi.
- **Food cost: IVA 10% hardcoded** anche per ricette a 22%, e `incidenza_media`
  come media di percentuali invece di `sum(fc)/sum(netto)`. Area a basso
  traffico (5 ricette).

## Come si lavora (CLAUDE.md + WORKFLOW.md §5)

1. **Una dimensione alla volta, chiusa davvero**: presidio provato per
   mutazione, commit, verbale, contatore ri-misurato, `check_documentazione.py`
   pulito.
2. **Un mutante per volta**, e verifica che il pattern esista davvero nel
   sorgente prima di dire "sopravvissuto".
3. **Un presidio chiama il codice vero.** Un test che ricalcola la formula, o
   che asserisce sul testo del sorgente, sopravvive al mutante. Per la logica
   frontend in `lib/` c'è `tests/helpers_ts.py`, che esegue il TypeScript vero
   con node.
4. **Si lavora su `main` locale**, niente branch né PR. Il push è di Mattia.
5. **Sessioni parallele sono la norma**: contale a fine sessione, non
   committare lavoro altrui (`git add -A` è il modo tipico di sbagliare).

## Trappole già pagate

- **Il gate Stop cerca `.claude/.reviewer_gate_ok`, che nessuno scrive mai**
  (`code-reviewer.md` non lo menziona e l'agente è di sola lettura). Il gate
  quindi ri-blocca a ogni commit nuovo, anche fatto per applicare i rilievi
  della review: si ferma solo per l'anti-loop sull'HEAD. **Da sistemare, ma è
  una decisione di Mattia** — tocca un hook e la definizione di un agente.
- **Mai lanciare la suite mentre un'altra sessione la sta girando**, e mai
  `git stash` con la suite in corso: produce rossi finti.
- **Prendi un baseline della suite prima di modificare**, o attribuirai a te
  rossi preesistenti. Il 05/09: 12.947 prima, 12.945 dopo (32 test rimossi coi
  moduli morti, 30 nuovi).
- **Un fix parziale lascia i consumatori indietro**: il 05/09 lo stesso difetto
  è stato corretto in due riprese perché il secondo chiamante era sfuggito.
  Cerca **tutti** i consumatori di un contratto che cambi.
