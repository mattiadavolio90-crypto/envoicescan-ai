#  ONEFLUX - Gestione Costi Ristorante

**Versione:** 5.5  
**Status:**  Produzione  
**Ultimo aggiornamento:** 19 Giugno 2026

---

##  Descrizione

Piattaforma SaaS per la gestione automatizzata dei costi di ristoranti e attività food & beverage.  
Analizza fatture elettroniche (XML, P7M, PDF), categorizza i prodotti con intelligenza artificiale e genera report dettagliati su margini e spese.

---

##  Funzionalità

- Analisi automatica fatture XML/P7M/PDF
- Ricezione automatica fatture SDI via Invoicetronic
- Categorizzazione prodotti con AI (OpenAI GPT-4o-mini)
- Dashboard margini mensili (Food, Beverage, Spese Generali)
- Confronto prezzi fornitori con alert configurabili per soglia
- Gestione multi-ristorante
- Sistema autenticazione sicuro (Argon2, sessioni con scadenza 30 giorni)
- Pannello amministratore per gestione clienti
- Recupero password via email
- Diario note per ristorante
- Sistema trial utenti con scadenza e gestione pagine abilitate
- Custom tag per classificazione manuale fatture
- Soft delete fatture con retention status
- Data competenza fattura separata dalla data documento
- Cache versioning per invalidazione coerente lato client
- Privacy Policy e Termini di Servizio integrati

---

##  Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Frontend/App | Next.js 16 (App Router) su Vercel |
| Database | Supabase (PostgreSQL) |
| Ingestion SDI | Invoicetronic + Supabase Edge Function |
| Worker API | FastAPI (Railway) |
| Queue worker | `python worker/run.py` (Railway, servizio dedicato) |
| AI | OpenAI GPT-4o-mini |
| Email | Brevo SMTP API |
| Password hashing | Argon2 |
| Hosting | Vercel (frontend) + Railway (worker) |
| Monitoraggio | GitHub Actions (uptime + coda ricavi) |

> **Nota:** Streamlit (`app.py` + `pages/`) è stato il frontend storico fino a giugno
> 2026; ora è dismesso. Il container Railway serve il worker FastAPI, non Streamlit.

### Topologia deploy (stato attuale)

- **Frontend Next.js** su Vercel (`app.oneflux.it`)
- **Worker FastAPI** su Railway (servizio `worker`): `/health`, `/api/*` — gate via `X-Worker-Key`
- **Queue worker** su Railway (servizio `queue-worker`): `python worker/run.py`, ingest coda fatture
- **Webhook Invoicetronic**: Supabase Edge Function con `verify_jwt=false` (dichiarato in `supabase/config.toml`), auth via firma HMAC-SHA256 + anti-replay
- Dettagli riproducibili in [docs/DEPLOY_RUNBOOK.md](docs/DEPLOY_RUNBOOK.md)

---

##  Avvio locale

**Worker FastAPI** (backend):
```bash
pip install -r requirements-lock.txt
python -m services.fastapi_worker        # API su :8000
```

**Frontend Next.js**:
```bash
cd apps/web
npm install
npm run dev                              # :3000
```

Il container di produzione installa le dipendenze Python da `requirements-lock.txt`.
Su Windows il lockfile esclude automaticamente uvloop, non supportato dalla piattaforma.
Guida servizi locali completa: [DEV_SERVICES_GUIDE.md](DEV_SERVICES_GUIDE.md).

---

##  Sicurezza e Backup

### Misure di sicurezza implementate
- Password hash Argon2 (m=65536, t=3)
- Sessioni con scadenza 30 giorni e token opachi generati con `secrets.token_urlsafe(32)`
- Rate limiting login (5 tentativi  blocco 15 min)
- Rate limiting reset password (5 min cooldown)
- Validazione magic bytes su file caricati (PDF, XML, P7M)
- Protezione XSS su dati utente
- Sanitizzazione input AI (anti prompt injection)
- Limite upload: max 100 file / 200 MB per sessione
- Budget giornaliero AI: max 1000 chiamate/giorno
- Rotazione log automatica: 50 MB / 10 backup
- PII rimossi dai log (GDPR Art. 32)
- XSRF protection attiva, CORS limitato a origin espliciti
- Cookie di sessione `httpOnly` + `secure` + `sameSite` (token mai esposto a JS)
- RLS attiva e forzata sulle tabelle con dati cliente; accesso applicativo solo via `service_role`
- Webhook fatture autenticato via HMAC-SHA256 + anti-replay (no dipendenza da chiavi JWT)
- Advisor Supabase: 0 ERROR sicurezza, 0 WARN performance (audit 19/06/2026)

### Strategia di Backup

| Componente | Backup | Frequenza |
|---|---|---|
| Database (Supabase) | Point in Time Recovery | Continuo |
| Codice sorgente | Repository Git | Ad ogni commit |
| Dipendenze | requirements-lock.txt | Ad ogni aggiornamento |

---

##  Test

```bash
python -m pytest tests/ -q                              # suite Python
deno test --allow-env --allow-net supabase/functions/**/*_test.ts   # Edge Functions
```

~9530 test Python (9533 passed, 1 skipped) + 18 test Deno (auth HMAC + routing
multi-sede del webhook fatture). La CI (`.github/workflows/tests.yml`) lancia entrambe
le suite su ogni push e pull request.

---

##  Matrice Agenti (Routing Rapido)

Usa questa tabella per scegliere subito l'agente corretto ed evitare sovrapposizioni.

| Quando serve | Agente consigliato | Non usare se... |
|---|---|---|
| Bug runtime, regressioni funzionali, problemi UX/performance applicativa | DEBUG APP INTERA | devi fare gate pre-push, compliance GDPR/cookie, o audit parity/resilience avanzato |
| Audit avanzato locale/cloud, resilienza integrazioni, idempotenza webhook/worker, reliability dati, observability | DEEP AUDIT | vuoi solo debug generalista o manutenzione documentale |
| Verifica prima del push (diff + test mirati + verdetto) | Test e Check Pre-Push | vuoi audit esteso operativo/compliance |
| Coerenza documentazione/config e cleanup file obsoleti | Audit Completo App e Cleanup | stai cercando bug runtime o audit resilienza avanzato |
| Privacy/GDPR/cookie policy e allineamento legale vs runtime | Privacy GDPR e Cookie Compliance | stai facendo debug tecnico o test pre-push |
| Riconciliazione fatture XML vs Supabase (righe/importi/scadenze) | Verifica Fatture XML | devi riclassificare in massa le categorie |
| Audit/riclassificazione categorie AI su Supabase | Audit Categorizzazioni Supabase | devi fare riconciliazione XML completa |
| Pianificazione nuova implementazione prima di scrivere codice | Pianificazione Implementazioni ONEFLUX | devi fare debug/audit/compliance già in corso |

Note operative:
- In caso di dubbio tra DEBUG APP INTERA e DEEP AUDIT: usa DEBUG per bug applicativi, DEEP AUDIT per rischi sistemici tra ambienti e resilienza operativa.
- Per task con piu aree, parti dall'agente piu specifico e poi delega il resto all'agente verticale corretto.

---

##  Licenza

Tutti i diritti riservati  ONEFLUX  2026
