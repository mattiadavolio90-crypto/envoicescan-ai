# Prompt per la sessione — Fase 8: mappa cache/snapshot e ordine di deploy

> **Come si usa.** Imposta **Opus**, senza `ultrathink`. Apri una sessione nuova
> e incolla la sezione «PROMPT». Il resto del file è contesto che la sessione
> leggerà da sola.
>
> **Perché Opus e non Fable** (`AUDIT_COPERTURA.md` diceva «Fable normale», ma
> quella riga è stata scritta quando L8 era solo una riga in tabella, prima di
> misurare il perimetro): qui il lavoro non è *scegliere bene i casi da eseguire*
> — quello era L6/L7, e lì `ultrathink` serviva — ma **tenere insieme una matrice
> grande**: 10 file backend × 132 file frontend × 3 tabelle di stato × 56 punti di
> invalidazione, dove il difetto è una **cella vuota** che si vede solo
> incrociando tre liste. È correlazione su molto materiale, ed è il lavoro in cui
> Opus rende di più. `ultrathink` non serve: il rischio è contare male, non
> ragionare poco.

> **Le cifre qui dentro sono misurate il 15/09/2026 e vanno RI-MISURATE, non
> ereditate.** Non è prudenza formale: nei due prompt precedenti le misure
> ereditate erano sbagliate **due volte su due** — L6 dichiarava «8 letture
> dell'ora senza fuso» (erano 6: due erano commenti) e «8 chiamate HTTP su 11
> senza timeout» (erano 0: il `timeout=` stava tre righe sotto, fuori dal grep per
> riga). Un numero di questo file che entra in un verbale senza essere ri-contato
> è un errore che si propaga.

---

## PROMPT (copia da qui)

Apri la **Fase 8 della sessione trasversale di audit: L8 — mappa cache/snapshot e
ordine di deploy**. È l'ottava delle nove lenti; L1, L3, L2, L4 sono chiuse il
14/09/2026, L5, L6 e L7 il 15/09/2026. Resta solo L9 dopo questa.

Leggi prima, in quest'ordine:
1. `DOCUMENTAZIONE/AUDIT_COPERTURA.md` → sezione «Lenti trasversali» (cosa è già
   coperto e con quale metro: **si riparte dal diff, non da capo**)
2. `WORKFLOW.md` §6 → come si conduce un audit **e la regola sul costo**
3. `docs/piani/PROMPT_FASE8_CACHE_E_ORDINE_DI_DEPLOY.md` → questo file: perimetro
   già misurato e trappole già pagate

**Il problema in una riga:** le lenti finora hanno chiesto «il numero è giusto?».
Questa chiede **«il numero è giusto ma il cliente sta vedendo quello di ieri?»** —
un valore corretto, calcolato bene, servito vecchio da una cache che nessuno ha
invalidato, o da uno snapshot scritto da un codice che nel frattempo è cambiato.
È l'unico modo in cui un dato giusto arriva sbagliato all'occhio di chi paga.

**Perché adesso.** È già successo, ed è in `CLAUDE.md` fra le trappole: dopo una
modifica alla logica del briefing, **senza bumpare `_BRIEFING_CODE_VERSION` il
cliente continua a leggere il testo vecchio** (cache giornaliera + TTL 30'). Quel
contatore è a **24** oggi: è stato bumpato a mano ogni volta, e «a mano» è
esattamente ciò che una lente deve verificare.

### Il perimetro, misurato il 15/09/2026 (ri-misuralo)

| Cosa | Misura | Dove |
|---|---|---|
| File backend che dichiarano una cache | **10** | `services/*.py`, `utils/*.py`, `config/*.py` |
| Occorrenze cache/TTL nel backend | **126** | idem |
| Punti che invalidano nel codice | **56** | `services/`, `worker/` |
| Funzioni trigger di bump a DB | **3** (`fn_bump_cache_version`, `…_fatture_documenti`, `…_fornitori_config`) | `supabase/schema_snapshot.sql` |
| File frontend con direttive di cache | **132** file, **165** occorrenze (`revalidate`, `unstable_cache`, `force-dynamic`, `no-store`) | `apps/web/src` |
| Tabelle di stato/snapshot vive | **3**: `cache_version` (3 righe), `daily_briefing_state` (53), `gruppo_segnali_state` (40) — **tutte scritte oggi** | DB live |
| Versione del briefing | `_BRIEFING_CODE_VERSION = 24` | `services/daily_briefing_service.py:135` |

Sono **candidati, non verdetti**. La prima cosa da fare è ridurre 126+165 a una
**matrice**: chi scrive un dato × quale cache lo serve × chi la invalida. Le celle
vuote della terza colonna sono la lente.

### Le tre domande che chiudono la lente

1. **Ogni scrittura ha il suo invalidatore?** Se un dato cambia e nessuna cache
   viene bumpata, per quanto tempo il cliente vede il vecchio? (Il TTL è la
   risposta, e va letto nel codice — non nel doc: `LOGICA_BRIEFING.md` sbagliava
   **6 soglie su 11**.)
2. **Uno snapshot è ancora prodotto dal codice che dice di essere?** Le tre
   tabelle di stato contengono numeri calcolati da una versione del codice. Se la
   formula è cambiata e lo snapshot no, **il cliente confronta due mondi**: c'è già
   un precedente chiuso in L3 (`gruppo_salute_componenti`).
3. **L'ordine di deploy può servire una pagina rotta?** Vercel parte **solo** se
   il commit tocca `apps/web/**`, Railway a **ogni** push (anche solo `.md`).
   Quindi frontend e worker si disallineano di routine: una pagina nuova che
   chiama una rotta non ancora deployata, o una rotta cambiata sotto un frontend
   vecchio. Le Edge Function **non si deployano affatto col push** (memoria:
   `edge-function-produzione-dietro-al-repo`).

### Il metro: si esegue, non si legge

- Una cache si prova **scrivendo il dato e rileggendo la pagina/endpoint**, non
  ispezionando il decoratore. Un `@cache` letto non dice quando scade davvero.
- Uno snapshot si confronta **ricalcolando la formula viva** sugli stessi input e
  diffando: se divergono, il cliente vede due numeri diversi per la stessa cosa.
- L'ordine di deploy si prova **sul diff dei path**: `git log --oneline
  origin/main..main` + quali toccano `apps/web/**`. Vale la memoria
  `coda-push-cambia-mentre-la-prepari`: la composizione scade in minuti.
- **Un presidio si prova per mutazione**, o non è un presidio. Verifica anche che
  il mutante si sia **applicato davvero** (memoria: `mutante-invalido…`).

### Vincoli, non negoziabili

- **Costo:** rilevatori e misure **in sessione**. Niente workflow multi-agente:
  l'unico sub-agente è il `code-reviewer` a fine fase (`WORKFLOW.md` §6). Un
  agente si usa **per contraddire**, non per moltiplicare — in L6 e L7 un
  refutatore ha smentito mie conclusioni **quattro volte**, ed erano difetti veri.
- **Non riprogettare la cache.** Un invalidatore mancante è un fix con mutante;
  una politica di cache nuova è una feature e si pianifica a parte.
- **Non pushare.** Si lavora su `main` locale. Misura tu la coda all'apertura
  (`git log --oneline origin/main..main`) e dillo a Mattia col numero e di chi
  sono i commit. Il push è una sua decisione, la sera.
- **Attenzione al briefing:** se tocchi la sua logica, **bumpa
  `_BRIEFING_CODE_VERSION`** — è la trappola che questa lente sta auditando, e
  sarebbe ironico inciamparci dentro.

### Criterio di chiusura

La lente è chiusa quando esiste **la matrice** (scrittura × cache × invalidatore)
con le celle vuote nominate una per una, ogni difetto vero è corretto **con un
mutante che muore**, il verbale è scritto, `DOCUMENTAZIONE/AUDIT_COPERTURA.md` ha
la riga L8 con le cifre ri-misurate, `check_documentazione.py` è pulito e il
`code-reviewer` è verde. Se il perimetro coperto è parziale, si scrive
**`parziale`** e si dice cosa è rimasto fuori.

---

## Contesto: cosa è già coperto (non rifarlo)

- **L3** ha già guardato i **monitor e i silenzi** in produzione, e ha corretto uno
  snapshot che divergeva (`gruppo_salute_componenti`). Qui si guarda la **cache**,
  non l'allarmistica.
- **L6** ha già coperto **tempo e concorrenza**: TTL scaduti per via del fuso sono
  suoi, non di questa lente. Ma il **cron delle 06:30 UTC al cambio d'ora del
  25/10/2026** è un residuo dichiarato in L6 che tocca anche qui.
- **L5** ha già inventariato **colonne e campi**: quali dati esistono è noto.

## Trappole già pagate (memoria del progetto)

- `soglie-doc-si-rimisurano-nel-codice` — il doc del briefing sbaglia 6 soglie su
  11: **leggi la costante**.
- `cifra-vive-in-piu-punti` — una cifra corretta dove guardavi resta sbagliata
  altrove: `grep` in tutto il repo.
- `strumento-costruito-e-mai-collegato` — una cache/RPC può avere **zero
  chiamanti**: cerca i call site escludendo i test.
- `test-che-legge-il-sorgente-non-prova-il-comportamento` — un assert su un
  decoratore non prova che la cache scada.
- `presidio-che-legge-git-si-skippa-in-ci` — se un test dipende dalla storia git
  serve `fetch-depth: 0`, e lo skip va reso rumoroso.
