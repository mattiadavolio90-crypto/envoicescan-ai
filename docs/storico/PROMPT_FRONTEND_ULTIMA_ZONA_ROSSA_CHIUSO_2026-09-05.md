> # ✅ CHIUSO — 05/09/2026
>
> **Esito, e le premesse che non hanno retto.** Il lavoro e' fatto, committato
> (`f3d4e89`, `6ba0d6e`, `cb058a6`) e **deployato**. Ma **entrambe le premesse di
> questo prompt erano sbagliate**, ed e' la parte che vale la pena ricordare:
>
> 1. **«4.069 righe rosse su 53.795»** — falso. Ri-misurato area per area il 05/09:
>    il rosso vero e' **3.316** su **53.855**. La differenza non e' lavoro fatto,
>    sono due errori di conteggio: le 4.871 righe di `app/api/` erano contate come
>    rosse **pur essendo gia' segnate «letto» dal 30/08 nello stesso file**, e una
>    riga «hooks + file diretti + proxy = 723» sommava perimetri sovrapposti.
>    Ora la colonna del contatore **chiude a scarto 0**.
> 2. **«`agenda/` muove soldi che finiscono nel MOL»** — falso, e gia' corretto una
>    volta in direzione opposta («0 turni a DB»). I 107 turni esistono, ma
>    `costo_orario` e' **NULL su 107/107**: l'area **muove 0 EUR**. Terza verita'
>    sulla stessa area in tre documenti diversi.
>
> **Cosa ha prodotto comunque valore:** la misura fatta per verificare la premessa
> ha trovato il buco vero, piu' grande dell'area rossa — il **costo del personale a
> zero su ago+set per 7 sedi su 7**, che rende il MOL di due mesi non confrontabile.
> Ed e' stato corretto un difetto reale nel ponte agenda→MOL: un «Recupera dal tab
> Personale» a vuoto **azzerava il costo nel MOL** (`toStr(0) === ""` svuotava il
> campo, il Salvataggio successivo scriveva 0). Presidi: 18 test nuovi, provati per
> mutazione.
>
> **Non aprire questo file come lavoro da fare.** Lo stato vivo sta in
> `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-09.md`; la revisione del modello turni
> chiesta da Mattia il 05/09 e' registrata li' in §5.

---

# Prompt sessione — l'ultima zona rossa: il frontend

> **Modello**: **Opus**, `ultrathink` in apertura — `agenda/` tocca il **costo del
> personale**, che entra nel MOL: è una regola di dominio, non una pagina di contorno.
> **Sforzo**: alto. È una dimensione di audit, non un fix.
> **Voce di roadmap**: §0 di `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-09.md`.

---

## Perché questa sessione

Il **backend è chiuso al 100%** il 5/09 (`70275cc`, `59ff32a`, `5fb12b7`): non
restano righe mai guardate in `services/`, `utils/`, `config/`, `worker/`.
**Tutto ciò che resta rosso è frontend: 4.069 righe** su 53.795.

Non è "il residuo": è l'unico posto dove un difetto può ancora vivere senza che
nessuno l'abbia mai cercato.

## ⚠️ La premessa che ha già smesso di valere

`AUDIT_COPERTURA.md:188` dice che `(app)/agenda/` è stata **scartata con misura**:
«**0 turni a DB**». Ri-misurato il **5/09 sera**:

| Tabella | Righe | Ultimo dato |
|---|---:|---|
| `turni_personale` | **107** | **05/09/2026** (oggi) |
| `dipendenti` | **4** | 04/09/2026 |
| `regole_turni_ricorrenti` | 0 | — |
| `marketplace_leads` | 0 | — |

**L'area si è popolata mentre il ciclo guardava altrove**, e i turni si caricano
*adesso*. Non solo: `turni_personale` ha `costo_orario`, `lordo_mensile`,
`ore_extra`, `importo_extra`, `importo_a_carico` — **muove soldi che finiscono nel
costo del personale**, quindi nel MOL. C'è già una memoria su questo
(«Personale a 0 sui mesi recenti»): il costo del personale mancante taglia gli
ultimi 1-2 mesi da ogni gate che lo richiede.

**Ri-misura comunque in apertura**: fra questo prompt e la sessione passeranno
giorni, e in questo ciclo **le cifre ereditate hanno sbagliato più volte di quelle
misurate**. La riga sopra è già la seconda verità su `agenda/`.

## Il perimetro, ri-misurato il 5/09 sera

| Area | Righe | Stato dichiarato | Cosa sappiamo |
|---|---:|---|---|
| `(app)/agenda/` | **694** | 🔴 | **la premessa è scaduta**: 107 turni, 4 dipendenti, dati di oggi, campi economici |
| `(auth)` + `(legal)` + `hooks/` + `assistenza/` + `style-guide/` | **1.697** | 🔴 | `assistenza` e `style-guide` restano plausibilmente vuote — **verifica, non dedurre** |
| resto (file diretti, proxy, `(demo)`, `globals.css`) | ~1.678 | 🔴 | da inventariare per differenza |
| **Totale rosso** | **4.069** | | su 53.795 di frontend |

Comandi (dal file `AUDIT_COPERTURA.md`, non inventarli):
```bash
git ls-files apps/web/src | grep -v -E '\.(woff|woff2|svg|png|jpg|ico)$' | xargs wc -l | tail -1
git ls-files "apps/web/src/app/(app)/agenda" | xargs wc -l | tail -1
```

## Da dove partire

1. **`(app)/agenda/` (694 righe)** — l'unica area rossa con **dati veri e recenti**,
   e l'unica che tocca importi. Prima il DB, poi il codice: quanti turni, quante
   sedi, che periodo, e se il costo che ne esce **quadra con quello che il MOL usa**.
2. Le altre aree **solo dopo aver misurato che hanno dati**. `agenda/` insegna che
   «tabella vuota» è una fotografia, non una proprietà.

## Il vincolo che decide come si lavora qui

**Il frontend non ha un runner npm** (`deploy-vercel.yml` scatta su `apps/web/**`:
un test deployerebbe). La rete sono **22 file `tests/test_*_frontend.py`** che
eseguono il TypeScript vero con node (`tests/helpers_ts.py`), e coprono **solo
`lib/`** — non rendering, hook, stato, effetti.

**Conseguenza pratica**: per testare logica che sta in un `.tsx`, va prima
**estratta in `lib/`**. È il metodo che ha chiuso `margini/`, `catena/`,
`scadenziario` e `dashboard/` — non un'invenzione di questa sessione.

## Cosa cercare (dove il ciclo ha trovato i difetti veri)

- **Importi e formati italiani**: il 01/09 erano sbagliati in **60 punti**, non ~25.
  Fonte unica: `lib/format.ts`.
- **Il guasto travestito da "nessun dato"**: `workerGet` torna `null` su ogni
  fallimento e un `?? []` lo trasforma in lista vuota. Fonte unica:
  `lib/esito-caricamento.ts` (fix R10). Il 5/09 lo stesso pattern è stato trovato
  **lato Python** nello scadenziario: cercalo in entrambe le direzioni.
- **Confronti di rotta**: `startsWith` non è un confronto di segmento — `/m` matcha
  `/margini`.
- **Percentuali e basi**: prima di dire che una percentuale non torna, guarda su
  quale chiave è definita. Somme multiple di 100 = stai aggregando fra gruppi.
- **Fix parziale**: quando cambi un contratto, cerca **tutti** i consumatori. Il
  5/09 lo stesso difetto è stato corretto in due riprese perché un chiamante era
  sfuggito, ed è successo di nuovo sul `pool` dei tag (4 consumatori, una fonte).

## Come si prova (o non vale)

- **Un presidio chiama il codice vero.** Un test che ricalcola la formula, o che
  asserisce sul testo del sorgente (`getsource`, `in src`), **sopravvive al
  mutante**: non è un presidio.
- **Un mutante per volta**, e prima verifica che il pattern **esista davvero** nel
  sorgente: se non esiste, "sopravvissuto" non misura niente.
- **Se un mutante sopravvive**, la causa può essere il *limite dello strumento* e va
  scritta: il 5/09 un mutante sull'`.order()` è sopravvissuto perché il fake
  restituisce sempre le righe in ordine di lista — dichiarato, non nascosto.

## Trappole già pagate (le ultime due sono nuove del 5/09)

- **Prendi il baseline della suite prima di modificare** (5/09: 12.989 → 12.995),
  e **ri-misura** il conteggio finale: rimuovendo codice morto spariscono i suoi
  test, e la differenza va spiegata addendo per addendo.
- **Mai lanciare la suite mentre un'altra sessione la sta girando**, e mai
  `git stash` con la suite in corso: rossi finti.
- 🆕 **Il backup per la mutazione va preso PRIMA del primo mutante.** Il 5/09 il
  `.bak` è stato copiato dopo una mutazione: ogni "ripristino" rimetteva il codice
  mutato, e **la suite completa è girata sul file sbagliato**. Dopo l'ultimo
  ripristino, verifica sempre con `git status` / `git diff`.
- 🆕 **Rimuovere codice morto NON è a rischio zero.** Il 5/09 il difetto peggiore
  della sessione non era nei due fix: cancellando una funzione cachata è rimasto
  orfano il suo `@_make_cache(ttl=60)`, che si è **riattaccato alla funzione
  successiva del file** — una *scrittura* finita dentro una cache. Quando togli una
  `def`, guarda cosa c'era **sopra** e cosa viene **sotto**.
- **Il gate Stop cerca `.claude/.reviewer_gate_ok`, che nessuno scrive mai**: ri-blocca
  a ogni commit, anche su quelli che applicano i rilievi della review. **Da sistemare,
  ma è una decisione di Mattia** — tocca un hook e la definizione di un agente.

## Rilievi aperti, da valutare (misurati, non urgenti)

Dal backend appena chiuso — nessuno visibile al cliente oggi:
- **`services/__init__.py:184`**: il `raise` sta dentro il `try` e viene ingoiato
  dall'`except Exception: pass` di `:188` — il messaggio diagnostico accurato non
  arriva mai. Solo diagnostica, ma il file è coperto dalla **regola #3** di CLAUDE.md.
- **Campanella notifiche** (`fastapi_worker.py:2767`): `.limit(100)` **prima** del
  filtro `dismissed_at` fatto in Python. Il cliente più avanti è a 33 su 100, ma
  28 su 33 sono già archiviate: l'accumulo va in quella direzione.
- **`ai_cost_service.py:86`**: `return 0` su errore DB fa risultare la quota AI
  sempre disponibile — un DB degradato **spegne il rate limit dei costi**.
- **`session_service.py:184`**: `revoca_tutte_sessioni` ritorna `0` sia su errore
  sia su "nessuna sessione": un logout globale fallito dopo cambio password è
  indistinguibile da uno riuscito. **Impatto di sicurezza.**
- **`_streamlit_shim.py`**: zero test, e `tests/conftest.py:48-52` lo sostituisce con
  un MagicMock a superficie **aperta** mentre in produzione la superficie è **chiusa**:
  nessun test esercita mai lo shim reale, e un `st.columns(2)` passerebbe verde in CI
  rompendo il worker.
- **`legacy_streamlit/`** (6 file, 2.771 righe) esiste ancora, mentre CLAUDE.md lo dà
  «rimosso dal repo il 17/7». Il doc è impreciso, e alcune funzioni sembrano vive
  solo perché chiamate da lì.

Ereditati dal 05/09 mattina, ancora aperti: `price_impact` con `impatto_mese` su due
scale diverse poi ordinate insieme; asimmetria `Da Classificare` fra
`fastapi_worker.py:8330` (filtra) e `:8215` (no) — misurato: 70 quote, 1.270,21 €;
food cost con IVA 10% hardcoded anche per ricette a 22%.

## Come si lavora (CLAUDE.md + WORKFLOW.md §5)

1. **Una dimensione alla volta, chiusa davvero**: presidio provato per mutazione,
   commit, verbale, contatore ri-misurato, `check_documentazione.py` pulito.
2. **Si lavora su `main` locale**, niente branch né PR. **Il push è di Mattia.**
3. **Sessioni parallele sono la norma**: contale a fine sessione, non committare
   lavoro altrui (`git add -A` è il modo tipico di sbagliare). Il 5/09 c'erano 3 file
   di altre sessioni nel working tree per tutta la durata del lavoro.
4. **A Mattia si risponde in 5 righe**: verdetto, max 3 punti, una domanda,
   «vuoi il dettaglio?».

## Stato al 5/09/2026 (sera) — punto di partenza

- Deploy fatto: `b5088e8..5fb12b7`, **18 commit** spediti (3 di questa sessione,
  15 di sessioni parallele). Toccano `apps/web`, quindi **sia Vercel sia Railway**
  hanno ridispiegato.
- Suite: **12.995 raccolti, 12.951 passed / 44 skipped / 0 failed**.
- Copertura: **backend 100%**, app **114.198 righe** totali, rosso **4.069 (4%)**,
  tutto e solo frontend. La colonna chiude a **scarto 0**, ri-misurata addendo per
  addendo.
