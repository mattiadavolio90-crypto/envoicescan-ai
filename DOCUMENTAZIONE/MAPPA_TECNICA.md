# ONEFLUX — Mappa tecnica

**A cosa serve questo file:** dire **dove** sta ogni cosa e **perché** è fatta
così. Non spiega *come* funziona il codice — quello lo dice il codice, che non
mente mai. Ogni volta che un documento ha provato a descrivere il funzionamento,
è andato fuori sync e ha fatto danni (la P.IVA sbagliata è ricomparsa 4 volte,
Streamlit è rimasto "attivo" nei doc per settimane dopo essere stato spento).

Le regole che non si possono violare stanno in `CLAUDE.md`, l'unico documento
sempre in contesto. Qui c'è la geografia.

> Manuale discorsivo per persone (non per chi scrive codice): chiedi a Claude
> "aggiorna il manuale" e viene rigenerato come pagina web dal codice corrente.
> Non esiste come file nel repo, di proposito: un manuale che si rigenera non
> può andare fuori sync.

---

## 1. Il flusso, in una riga

```
Fattura (SDI o upload) → parsing → categorizzazione AI → DB → margini/report
```

Tutto il resto del prodotto è al servizio di questa catena.

---

## 2. Dove sta cosa

| Devi toccare… | Vai in… |
|---|---|
| Una pagina che il cliente vede | `apps/web/src/app/(app)/<pagina>/` |
| Il mobile | `apps/web/src/app/m/` — è un **sottoinsieme separato**, non responsive |
| Una chiamata API dal frontend | `apps/web/src/app/api/**/route.ts` (158 route, solo proxy) |
| Logica di business | `services/*.py` |
| Un endpoint del worker | `services/routers/*.py` (12 router) |
| Schema DB | `supabase/migrations/` (canonico) |
| Ricezione fatture SDI | `supabase/functions/invoicetronic-webhook/` (Deno) |
| Costanti, categorie, prompt | `config/` |

### I servizi che contano

| File | Ruolo |
|---|---|
| `ai_service.py` | Categorizzazione righe fattura |
| `invoice_service.py` | Parsing FatturaPA + guardrail |
| `daily_briefing_service.py` | Briefing Home (cosa dire, in che ordine) |
| `price_impact_service.py` | Alert prezzi per **impatto** (peso × aumento) |
| `margine_service.py` | MOL, food cost, margini |
| `multisede_routing.py` | Smista fatture fra sedi con la stessa P.IVA |
| `notification_service.py` | Costruisce le notifiche |
| `auth_service.py` / `session_service.py` | Auth custom (non Supabase Auth) |

### I router del worker

`account` · `admin` · `cestino` · `fatture` · `gruppo` · `margini` · `prezzi` ·
`ricavi` · `riparto` · `scadenziario` · `tag` · `workspace`

`services/fastapi_worker.py` (~7.700 righe) tiene ancora briefing, KPI Home e
infrastruttura. Non è un errore da correggere di corsa: lo split è già stato
fatto una volta (11.190 → 4.400 righe) e un tentativo di scorciatoia con
`__getattr__` ha rotto 9 router in produzione. Se lo tocchi, usa wrapper
espliciti.

---

## 3. Perché è così (le decisioni che non si leggono dal codice)

**Il frontend non calcola niente.** Next.js proxia e disegna; ogni conto sta nel
worker. Motivo: un solo posto dove la logica può divergere. Le 158 route in
`api/*` sono deliberatamente stupide.

**Il worker è separato dalla coda.** `worker` (FastAPI, HTTP) e `queue-worker`
(`worker/run.py`, nessuna porta) sono due servizi Railway dalla stessa immagine,
distinti solo dallo Start Command. Motivo: un ingest pesante non deve rallentare
le pagine. `WORKER_ENABLED=0` sul queue-worker è un killswitch — a `0` la coda
non si drena e gli incassi dei clienti spariscono (successo il 9-11/06).

**L'AI non decide mai, riscrive soltanto.** Nel briefing il codice produce frasi
già complete coi numeri giusti; l'AI cambia solo il tono e ha il divieto di
toccare cifre. Motivo: un numero sbagliato nel "buongiorno" distrugge la fiducia
del cliente in modo irreparabile. Vale anche per la chat (tool read-only).

**La categorizzazione è onesta.** Se nessuno riconosce una riga, resta
`"Da Classificare"` ed **esce dai margini**. Motivo: una categoria inventata
falsa il MOL, e un MOL falso è peggio di un MOL mancante. Vedi `CLAUDE.md` §1-2.

**Gli alert prezzi usano Pareto, non una % fissa.** Solo i prodotti che cumulano
l'80% della spesa sono eleggibili, così ci si adatta a clienti concentrati o
frammentati senza soglie magiche. I **tag** invece non hanno filtro di peso: se
il cliente ha creato un tag, ci tiene.

**Auth custom, non Supabase Auth.** `auth.uid()` è **sempre NULL** e l'accesso
passa da `service_role_key`, che bypassa RLS. Conseguenza critica: i filtri
`user_id`/`ristorante_id` in Python **sono** la sicurezza multi-tenant, non un
di più. RLS è solo la seconda rete.

**Il briefing è cache giornaliera.** Un deploy non la invalida da solo oltre il
`_BRIEFING_CODE_VERSION`: se cambi la logica, bumpa quella costante. Altrimenti
il cliente vede il testo vecchio col codice nuovo.

**Streamlit è congelato, non morto.** `app.py`, `pages/`, `components/` restano
nel repo ma non sono serviti a nessuno dallo switch DNS dell'8/6/2026. Non
aggiungerci nulla.

---

## 4. Le trappole (costano ore se non le sai)

| Trappola | Cosa succede |
|---|---|
| Query senza `filter_active()` | Vedi anche le fatture nel cestino |
| Modifica al briefing senza bumpare `_BRIEFING_CODE_VERSION` | Il cliente vede il testo vecchio |
| Deploy in orario di lavoro | I clienti sono dentro l'app: solo sera/notte/mattina presto |
| Worker locale senza `--reload` | Tiene in memoria il codice vecchio: va riavviato |
| Next.js locale | Punta al **DB cloud reale**: scrivi sui dati veri dei clienti |
| Migration in `migrations/` | Cartella **congelata** (001→082). Il canonico è `supabase/migrations/` |
| `__getattr__` per gli helper dei router | Ha già rotto 9 router in produzione (PEP 562). Usa wrapper espliciti |
| Modifica solo desktop | `/m` è separato: va allineato a mano |

---

## 5. Stato noto (verificato 17/7/2026)

- **Aperto:** `services/notification_service.py:999` fa ancora `.limit(50000)` —
  è un obiettivo dichiarato e mai eseguito della Fase 1a del piano stabilità
  worker (`DOCUMENTAZIONE/PIANO_STABILITA_WORKER_2026-07-02.md`).
- **Aperto:** il dedup dell'upload confronta il **nome** del file, non il
  contenuto.
- **Aperto:** la card "I conti del gruppo" può mostrare numeri gonfiati quando
  più sedi non hanno i costi (vedi `LOGICA_BRIEFING.md` §8).

---

## 6. Gli altri documenti, e quando servono

| Documento | Quando aprirlo |
|---|---|
| `CLAUDE.md` | Sempre — è il contratto, già in contesto |
| `LOGICA_BRIEFING.md` | Per cambiare **cosa dice** il briefing (soglie, priorità, tono) |
| `docs/DEPLOY_RUNBOOK.md` | Per ricreare/verificare i servizi Railway |
| `DOCUMENTAZIONE/RUNBOOK_INCIDENTI.md` | Quando arriva un alert |
| `DOCUMENTAZIONE/tecnica/DATABASE_SCHEMA.md` | Per lo schema tabella per tabella |
| `DOCUMENTAZIONE/tecnica/AI_PIPELINE.md` | Per la pipeline di classificazione |
| `DOCUMENTAZIONE/tecnica/CHAT_ASSISTENTE.md` | Per la chat AI (tool, limiti) |
| `DOCUMENTAZIONE/tecnica/TROUBLESHOOTING.md` | Quando qualcosa non parte |
| `docs/COMPLIANCE_GDPR.md` | Per domande legali/privacy |
| `docs/storico/` | Solo per problemi già visti (diagnosi Invoicetronic) |

---

*La verità di questo file è verificata da `tests/test_documentazione_onesta.py`.
Se lo modifichi con affermazioni false su simboli, percorsi o P.IVA, i test
diventano rossi.*
