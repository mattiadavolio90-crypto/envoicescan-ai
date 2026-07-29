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
| `notification_inbox_service.py` | Costruisce le notifiche |
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

**Streamlit non c'è più.** Dismesso l'8/6/2026, **rimosso dal repo il 17/7/2026**:
`app.py`, `pages/`, `components/`, `controllers/`, `static/` e i due servizi che
usava solo lui (`email_service`, `notification_service`) sono in git history.
Rimosso anche dalle dipendenze: il container non lo installa più.

Restano `import streamlit as st` dentro `services/`: **non è codice vivo**.
`services/_streamlit_shim.py` sostituisce il pacchetto con un guscio vuoto
(`session_state` = dict, `secrets` da env, rendering no-op) prima che i moduli
vengano importati. Motivo per cui lo shim esiste invece di ripulire i 206 `st.`:
sono dentro `upload_handler`, `ai_service`, `invoice_service` — il codice che
processa le fatture dei clienti. Riscriverlo per estetica è rischio senza
beneficio; lo shim costa zero e non mente.

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

- **Chiuso come falso allarme (17/7):** "il dedup dell'upload guarda il nome
  non il contenuto" era segnato come bug. Verificato sui dati reali: il nome SDI
  (`IT<piva-emittente>_<progressivo>.xml`) **contiene già la P.IVA di chi emette**,
  quindi è univoco per costruzione. Su 24.776 righe: **zero** nomi file associati a
  due fornitori diversi, e zero casi di stesso nome con documento diverso.
  Un dedup su `piva+data+totale` sarebbe **peggio**: cancellerebbe fatture vere
  (Amazon ha 4 fatture identiche da 69,85€ lo stesso giorno — 4 ordini reali).
- **Chiuso (17/7):** la card "I conti del gruppo" non mostra più numeri gonfiati
  quando più sedi non hanno i costi — cascata a 3 livelli (nessuno/food/completo),
  verificata su SUSHILAND (vedi `LOGICA_BRIEFING.md` §8).
- **Chiuso come falso allarme:** il `.limit(50000)` in `notification_service.py`,
  bersaglio della Fase 1a del piano stabilità worker, non è mai stato un problema
  di produzione: quel modulo è raggiungibile solo da Streamlit dismesso. Un
  "bug aperto" può sparire perché il codice che lo conteneva è uscito dal
  percorso servito — verificare i chiamanti prima di ottimizzare.

---

## 6. Indice completo — ogni documento del repo, per domanda

Questa è la **mappa unica**: se un documento esiste nel repo e non è qui, è un
segnale che va spostato/archiviato/eliminato, non ignorato. Organizzata per
"cosa devo fare", non per cartella — la cartella fisica conta meno di trovarlo.

**Come sono divise le due cartelle documentazione** (motivo storico, non
riordinabile senza toccare CI/Docker — vedi nota in fondo): `DOCUMENTAZIONE/`
= riferimento tecnico su come è fatto il prodotto oggi; `docs/` = processo
operativo (deploy, compliance, piani di lavoro correnti, know-how su incidenti
chiusi). Nella dubbio "dove metto un nuovo file", usa questo criterio.

### Voglio capire l'architettura / le regole di dominio
| Documento | Quando aprirlo |
|---|---|
| `CLAUDE.md` | Sempre — è il contratto, già in contesto |
| `DOCUMENTAZIONE/MAPPA_TECNICA.md` (questo file) | Dove sta cosa e perché è fatto così |
| `ONEFLUX_MASTER.md` | Visione, filosofia prodotto, modello commerciale — cosa non cambia a ogni deploy |

### Voglio lavorare su una feature (implementazione)
| Documento | Quando aprirlo |
|---|---|
| `WORKFLOW.md` | Come si pianifica/esegue (plan mode, `docs/piani/PIANO_<feature>.md`, modello per fase) |
| `scripts/check_documentazione.py` | A fine feature (WORKFLOW.md §6): trova documenti chiusi da archiviare/eliminare, link rotti, indice fuori sync |
| `IMPLEMENTAZIONI.md` | Roadmap feature future non ancora iniziate |
| `docs/piani/PIANO_<feature>.md` | Solo se esiste — lavoro multi-sessione in corso ora (git-ignorato, effimero) |
| `LOGICA_BRIEFING.md` | Per cambiare **cosa dice** il briefing Home (soglie, priorità, tono) |

### Voglio capire un dominio tecnico specifico
| Documento | Quando aprirlo |
|---|---|
| `DOCUMENTAZIONE/tecnica/DATABASE_SCHEMA.md` | Schema tabella per tabella |
| `DOCUMENTAZIONE/tecnica/AI_PIPELINE.md` | Pipeline di classificazione fatture |
| `DOCUMENTAZIONE/tecnica/CHAT_ASSISTENTE.md` | Chat AI (tool, limiti) |
| `DOCUMENTAZIONE/tecnica/BRIEFING_HOME.md` | Come è costruito tecnicamente il briefing (non cosa dice — quello è `LOGICA_BRIEFING.md`) |
| `DOCUMENTAZIONE/tecnica/DEPLOY_INFRASTRUTTURA.md` | Come sono collegati Vercel/Railway/Supabase |
| `DOCUMENTAZIONE/tecnica/SICUREZZA_GDPR.md` | Misure di sicurezza tecniche (non il dossier legale — quello è `docs/COMPLIANCE_GDPR.md`) |
| `DOCUMENTAZIONE/tecnica/PAGINA_SERVIZI_MARKETING.md` | La pagina pubblica "servizi" |
| `DOCUMENTAZIONE/tecnica/TROUBLESHOOTING.md` | Quando qualcosa non parte in locale |

### Qualcosa non va (incidente in produzione)
| Documento | Quando aprirlo |
|---|---|
| `DOCUMENTAZIONE/RUNBOOK_INCIDENTI.md` | Quando arriva un alert — primo posto dove guardare |
| `docs/DEPLOY_RUNBOOK.md` | Per ricreare/verificare i servizi Railway da zero |
| `docs/storico/` | Solo se il problema somiglia a uno già visto (diagnosi Invoicetronic, migration legacy) — indice in `docs/storico/README.md` |

### Voglio setup locale / comandi
| Documento | Quando aprirlo |
|---|---|
| `DEV_SERVICES_GUIDE.md` | Avviare worker/queue-worker/Next.js in locale |
| `README.md` | Descrizione pubblica del progetto (anche per chi non sviluppa) |

### Legale, GDPR, business
| Documento | Quando aprirlo |
|---|---|
| `docs/COMPLIANCE_GDPR.md` | Dossier GDPR completo — anche per audit/richieste clienti B2B |
| `docs/business-plan-costi.md` | Costi infrastruttura, pricing interno |

### Marketing, brand, roadmap commerciale
| Documento | Quando aprirlo |
|---|---|
| `PIANO_WEB_MARKETING.md` | Piano SEO/marketing vivo, 4 pilastri, si aggiorna nel tempo |
| `BRIEF_LANDING_ONEFLUX_1.md` | Copy/stile validato della landing pubblica |
| `GRUPPO_ACQUISTO.md` | Concept prodotto "gruppo d'acquisto" (non ancora costruito) |
| `LOGO.md` | Tool per rigenerare logo/wordmark |

### Storico riusabile (problemi chiusi con valore predittivo)
| Documento | Cosa insegna |
|---|---|
| `docs/storico/README.md` | Indice — criterio di cosa sta lì e perché |
| `docs/storico/INVOICETRONIC_DIAGNOSI_2026-07-02.md` | Precedenza Codice Destinatario su cassetto fiscale, conflitto multi-provider |
| `docs/storico/DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md` | Sandbox-vs-live Invoicetronic, bug P7M byte nulli |
| `docs/storico/MIGRAZIONE_APP.md` | Come fu fatto lo switch Streamlit → Next.js |
| `docs/storico/CHECKLIST_069_072.md` | Migration legacy applicate (cartella `migrations/` congelata) |
| `docs/storico/WEBHOOK_PARSER_BODY_2026-07-22.md`, `WEBHOOK_SCARTO_SILENZIOSO_2026-07-21.md` | Pattern di debug sui webhook Edge Function |

### Stato/decisioni tra sessioni (non file — memoria persistente)
Lavori chiusi, decisioni prese, contesto cliente: **non stanno più in file
`.md` nel repo**, stanno nella memoria auto-persistente di Claude Code
(`memory/project_*.md`, `memory/feedback_*.md`, `memory/reference_*.md`,
fuori dal repo). Un file `.md` di stato/riepilogo nel repo che non ha valore
predittivo futuro (vedi criterio in `docs/storico/README.md`) va eliminato
dopo che il suo contenuto è confluito in memoria, non tenuto "per sicurezza".

> **Nota sulla separazione `DOCUMENTAZIONE/` vs `docs/`:** non è stata unificata
> in una sola cartella perché 4 GitHub Actions, 2 Dockerfile/`.dockerignore` e
> `tests/test_documentazione_onesta.py` (`DOC_VIVI`) hanno percorsi hardcoded
> su entrambe — un merge fisico è rischio CI per un guadagno solo estetico.
> Se in futuro si fa, va fatto in un commit dedicato che aggiorna tutti quei
> riferimenti insieme, mai come effetto collaterale di un altro lavoro.

---

*La verità di questo file è verificata da `tests/test_documentazione_onesta.py`.
Se lo modifichi con affermazioni false su simboli, percorsi o P.IVA, i test
diventano rossi.*
