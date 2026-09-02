# ONEFLUX — Contesto per Claude Code

## Cos'è il progetto
Piattaforma SaaS (prodotto v5.5) per la gestione automatizzata dei costi di ristoranti.
Analizza fatture elettroniche XML/P7M/PDF, categorizza prodotti con AI (GPT-4.1-mini),
genera report su margini, prezzi fornitori, foodcost.

**Owner:** Mattia D'Avolio — sviluppatore singolo.
**In produzione dal 1 luglio 2026.** 7 account cliente attivi / 11 punti vendita
(misurato il 29/8/2026): 4 con migliaia di righe fattura e accesso nell'ultima
settimana, gli altri con pochi dati.

> Le cifre di questo file vanno **ri-misurate**, non ereditate: il 29/8/2026 la
> riga sopra diceva ancora «2 clienti in test» e «go-live: 1 luglio» a due mesi
> dalla data. Un file che entra in ogni sessione propaga i suoi errori ovunque.

---

## Architettura attuale

Il frontend di **produzione è Next.js** su Vercel (`app.oneflux.it`). Streamlit è
stato dismesso con lo switch DNS dell'8/6/2026 e **rimosso dal repo il 17/7/2026**
(`app.py`, `pages/`, `components/`, `controllers/`, `static/`): se ti serve, sta
nella git history. Il container Railway serve il worker FastAPI.

> I moduli di `services/` fanno ancora `import streamlit as st`, ma il pacchetto
> **non è installato**: `services/_streamlit_shim.py` lo sostituisce con un guscio
> vuoto. Non reintrodurre la dipendenza; gli `st.` residui sono no-op.

| Layer | Percorso | Note |
|---|---|---|
| Frontend (produzione) | `apps/web/` | Next.js 16 (App Router) su Vercel — 14 aree app + auth/legal/mobile, 170 route API |
| Business logic | `services/*.py` | DB, AI, upload, notifiche, documenti, margini |
| Utilità | `utils/*.py` | Formatters, validatori, helpers |
| Configurazione | `config/*.py` | Costanti, logger, prompt AI |
| Worker API | `services/fastapi_worker.py` (8.749 righe) | FastAPI — `/health`, `/api/*`; logica nei router `services/routers/*.py` |
| Worker async | `worker/run.py` | Processo separato (queue-worker) per operazioni pesanti |
| Edge Functions | `supabase/functions/` | Deno — `invoicetronic-webhook`, `ricavi-email-webhook` |
| Migrations | `supabase/migrations/*.sql` (canonico, 138 file) | Schema PostgreSQL, RLS, trigger. `migrations/*.sql` è LEGACY storico, 91 file su numerazione `001`–`082` (vedi `migrations/_LEGGIMI_STATO.md`) |
| Test | `tests/*.py` | 12.633 test pytest (molti parametrizzati) + 101 test Deno per le Edge Functions. Sul frontend: nessun runner npm — vedi Trappole |

**Database:** Supabase PostgreSQL — chiave `service_role_key` (bypassa RLS).
`auth.uid()` è sempre NULL — auth custom, non Supabase Auth.

---

## Regole di dominio critiche — NON violare mai

1. **Flusso categorizzazione = onesto** (rev. 23/06): una riga si classifica SOLO se dizionario/regole o l'AI la riconoscono con sicurezza. Se nessuno ci riesce resta `"Da Classificare"` (stato esplicito, visibile al cliente dal filtro "Da classificare" in Analisi Fatture → tab Articoli, con `needs_review=True`). **NIENTE fallback travestito in `"SERVIZI E CONSULENZE"`** (vecchio comportamento, eliminato). Il constraint DB ora è `fatture_categoria_not_empty_chk` (vieta solo NULL/vuoto, consente `"Da Classificare"`). Costante: `CATEGORIA_NON_CLASSIFICATA` in `config/constants.py`; `CATEGORIA_FALLBACK` ne è alias. Attenzione grafia: la variante errata `'Da Clasificare'` (una sola "s") resta sbagliata. Le righe `Da Classificare` sono escluse dai margini finché non vengono classificate (per non falsare il MOL).
2. **`"📝 NOTE E DICITURE"`** è consentita SOLO per righe con `totale_riga == 0`. Una dicitura con importo != 0 NON può restare in NOTE: il guardrail (`_applica_guardrail_note_con_importo`) la riporta a `"Da Classificare"` (non più SERVIZI), così resta visibile in coda e non entra nei margini con una categoria inventata.
3. **Chiave Supabase**: usare sempre `service_role_key` (non `key`) — non toccare `services/__init__.py` senza capire l'auth flow.
4. **`ADMIN_EMAILS`** normalizzato lowercase — confronti email sempre `.strip().lower()`.
5. **Soft delete**: query su `fatture` e `prodotti` devono filtrare `deleted_at IS NULL`. Usare `filter_active()` da `services.db_service`. Non rimuovere `.not_.is_("deleted_at", "null")` nelle query cestino (quelle sono intenzionali).
6. **Worker separato**: operazioni pesanti (classificazione AI, parsing fatture) vanno nel worker FastAPI / queue-worker — il frontend Next.js non esegue logica pesante, chiama le route `/api/*` del worker.

---

## Dove si lavora: su `main` locale, e basta

**Tutte le sessioni della giornata committano su `main` locale. Niente branch,
niente PR.** La sera, quando Mattia lo dice: **un push, un deploy**. Una sessione
nuova parte da `main`, mai dal branch di un'altra; se un branch esiste già e il
lavoro va spedito, riportalo su `main` in locale e chiudilo **senza** mergiarlo.

**Un branch si apre per UNA sola ragione**: quel lavoro **potrebbe non essere
spedito** (esperimento, refactor incerto). **Non** per la dimensione — un lavoro
da tre giorni su 40 file che va spedito comunque sta su `main` come un fix da due
righe. Con un branch per sessione le PR si impilano e la sera diventano N merge
in ordine obbligato: l'opposto del deploy unico. Il controllo non si perde:
finché non si pusha il lavoro non esiste per nessuno, e il `code-reviewer` gira
sul cumulativo prima del push. Vedi `WORKFLOW.md` §0.

---

## Come si risponde a Mattia

Mattia è l'owner, non un lettore di codice: decide **cosa** si fa, non come — le
spiegazioni tecniche lunghe non lo aiutano a decidere, lo bloccano.

**Quando chiede lo stato** («a che punto siamo», «abbiamo finito», «cosa manca»,
«recap»): **una riga di verdetto**, **max 3 punti** aperti (una riga ciascuno),
**una sola domanda** se serve una sua decisione, e **«Vuoi il dettaglio?»**.
Tetto ~10 righe, niente tabelle/codice/percorsi con numero di riga.

Il criterio non è quanto so, è **cosa gli serve per decidere il prossimo passo**:
se una frase non cambia cosa farà adesso, si taglia anche se è vera. Un mio errore
si corregge in **mezza riga**, non in cima e non in un paragrafo. Il dettaglio si
dà per intero **se lo chiede dopo**. Vale in **ogni** sessione, anche quando non
lo ricorda — `WORKFLOW.md` §1bis.

**A fine planning** (`ExitPlanMode`), sempre e senza che lo chieda: riepilogo non
tecnico **+ tabella fase / modello / sforzo**. `ultrathink` (parola nel messaggio,
non un menu) su apertura, audit e fix a una regola di dominio; normale
sull'esecuzione. Dettaglio: `WORKFLOW.md` §1ter e §3.

**Una cosa alla volta, chiusa davvero.** Non si apre una dimensione nuova finché
la precedente non è provata per mutazione, **committata**, con verbale, contatore
`AUDIT_COPERTURA.md` aggiornato e `check_documentazione.py` pulito — niente piani
a metà in `docs/piani/`. Dettaglio: `WORKFLOW.md` §5bis.

---

## Dove trovare il resto

Questo file è l'unico sempre in contesto: contiene solo ciò che, se ignorato,
rompe qualcosa. Tutto il resto sta altrove e si apre alla bisogna:

| Serve… | Documento |
|---|---|
| Come si lavora a una feature (planning/esecuzione, modello-per-fase, gate deploy) | `WORKFLOW.md` |
| Dove sta cosa, e perché è fatto così | `DOCUMENTAZIONE/MAPPA_TECNICA.md` |
| Cambiare cosa dice il briefing (soglie, priorità, tono) | `LOGICA_BRIEFING.md` |
| Schema DB, pipeline AI, chat, sicurezza, troubleshooting | `DOCUMENTAZIONE/tecnica/` |
| Deploy Railway, incidenti | `docs/DEPLOY_RUNBOOK.md`, `DOCUMENTAZIONE/RUNBOOK_INCIDENTI.md` |
| Visione, filosofia, modello commerciale | `ONEFLUX_MASTER.md` |
| Roadmap feature | `IMPLEMENTAZIONI.md` |
| Tutto il resto (marketing, GDPR, business plan, storico incidenti) | Indice completo in `DOCUMENTAZIONE/MAPPA_TECNICA.md` §6 |

> La documentazione viva è protetta da `tests/test_documentazione_onesta.py`: se
> un doc cita un simbolo o un percorso che non esiste più, il test fallisce — è
> l'unico modo perché un .md non menta per mesi in silenzio.

**Migrazione Next.js: COMPLETATA** (switch DNS 8/6/2026), mobile incluso (`/m`).
Streamlit è congelato: non estenderlo.

---

## Comandi utili

```powershell
python -m pytest tests/                         # suite Python
cd apps/web; npm install; npm run dev          # frontend Next.js :3000
python -m services.fastapi_worker              # worker FastAPI :8000

# Schema OpenAPI: esporta (dopo modifiche a fastapi_worker.py) / verifica drift
python scripts/export_openapi.py
python scripts/export_openapi.py --check-drift   # guida completa: DEV_SERVICES_GUIDE.md
```

---

## Trappole che sono già costate ore

- **Briefing:** dopo una modifica alla logica, **bumpa `_BRIEFING_CODE_VERSION`**
  o il cliente continua a vedere il testo vecchio (cache giornaliera + TTL 30').
- **Il deploy È l'arrivo del codice su `origin/main`**: **un commit locale non
  deploya niente**, è il `push` a spedire. Le due pipeline differiscono:
  **Vercel** parte solo se il commit tocca `apps/web/**` (`deploy-vercel.yml`,
  `paths:`); **Railway** non ha filtro di path — anche soli `.md` gli fanno
  ridispiegare il worker (config sul dashboard, non nel repo: `railway.toml`
  documenta i servizi, non il trigger). Non esiste un "spedisco ora, deployo
  stasera": la finestra oraria (sera/notte/mattina presto) è un vincolo **sul
  push**, salvo conferma esplicita di Mattia. Vedi `WORKFLOW.md` §0.
- **Mai `git push` / `gh pr create` / `gh pr merge` di iniziativa.** N sessioni ≠
  N deploy: il push manda **tutti** i commit accumulati (`git log --oneline
  origin/main..main`).
- **Più sessioni in parallelo sono la norma.** Commit e file non tuoi sono lo
  stato atteso, non un allarme: si contano e si riportano a fine sessione («in
  coda: 7 commit, 3 miei»). Mai committare lavoro non tuo (`git add -A` è il modo
  tipico di farlo per sbaglio). Se segnali un rischio che nasce da lavoro altrui
  di' sempre **di chi è** e **chi deve agire**, o Mattia lo legge come una tua
  dimenticanza e ti fa chiudere roba non tua. Vedi `WORKFLOW.md` §0.
- **Next.js in locale punta al DB cloud reale**: scrivi sui dati veri dei clienti.
- **Worker locale senza `--reload`** tiene in memoria il codice vecchio: riavvialo.
- **Mai `__getattr__`** per gli helper dei router: ha già rotto 9 router in produzione
  (PEP 562 non risolve i global lookup interni). Usa wrapper espliciti.
- **`/m` è un frontend separato**, non responsive: va allineato a mano.
- **Il frontend ha una rete, ma copre solo la logica pura.** Niente runner npm
  (`deploy-vercel.yml` scatta su `apps/web/**`: deployerebbe a ogni test). Sono
  **22 file `tests/test_*_frontend.py`** che eseguono il TypeScript vero con node
  (`tests/helpers_ts.py`): coprono `lib/`, **non** rendering, hook, stato ed
  effetti. Per testare logica in un `.tsx`, va prima estratta in `lib/`.
- **Né `tsc` né un test verde provano che il codice funzioni.** `tsc --noEmit`
  controlla i tipi e non esegue niente (29/8: soglia misurata dopo i filtri client,
  non scattava su nessuno dei 3 casi reali; 2/9: pulsante verso la pagina sbagliata).
  Restano verdi sul bug anche un **mock generoso** (i test del radar passavano su
  `fatture_documenti.upload_id`, colonna mai esistita) e un test che assicura sul
  **testo del sorgente**. **Un presidio si prova per mutazione**, o non è un presidio.

---

## Convenzioni di codice

- Nessun commento nel codice se non per motivi non ovvi
- `filter_active()` da `services.db_service` per tutte le query con soft-delete
- Le migration SQL vanno SOLO in `supabase/migrations/` con nome timestamp `AAAAMMGGHHMMSS_nome.sql` (formato Supabase CLI). La cartella `migrations/` (numerazione `001`–`082`) è storica e congelata: non aggiungere file lì. Stato reale applicato = DB live, non i file.
- I file in `scripts/` e `tools/` sono operativi/manutentivi — non fanno parte del runtime

---

## Sicurezza

- Password: Argon2id (m=65536, t=3, p=4) — non cambiare parametri. Sono espliciti
  in `services/auth_service.py` e asseriti da `tests/test_auth_argon2_parametri.py`:
  se li cambi lì senza aggiornare questa riga, i test falliscono (e viceversa)
- Sessioni: token `secrets.token_urlsafe(32)`, scadenza 30 giorni
- Rate limiting login: 5 tentativi → blocco 15 min
- File upload: validazione magic bytes (PDF, XML, P7M)
- Non esporre `SUPABASE_KEY`, `OPENAI_API_KEY` lato client
