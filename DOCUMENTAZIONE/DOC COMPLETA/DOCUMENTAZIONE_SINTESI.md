# ONEFLUX — Documentazione Sintetica

**Sistema SaaS di Analisi Fatture e Controllo Costi per la Ristorazione**

Versione: 6.0 | Aggiornamento: 5 Giugno 2026 | Autore: Mattia D'Avolio
Titolare: Recoma System S.r.l. (P.IVA IT09599210961)
Frontend: `nuovo.oneflux.it` (Next.js) | Legacy: `app.oneflux.it` (Streamlit)

---

## 1. Cos'è ONEFLUX

Piattaforma SaaS AI-first per ristoratori italiani. Automatizza l'analisi delle fatture dei fornitori: da XML/P7M/PDF grezzi a dashboard di controllo costi, margini e briefing AI giornaliero. Non è un gestionale — è un assistente di gestione economica.

**Funzionalità principali:**
- Ricezione automatica fatture SDI via Invoicetronic (codice `7HD37X0`)
- Classificazione AI in 31 categorie (600+ keyword + GPT-4o-mini)
- Dashboard KPI, pivot mensili per categoria e fornitore
- Calcolo MOL con centri di produzione (FOOD/BEVERAGE/ALCOLICI/DOLCI)
- Import ricavi da gestionali (XLS Passbi v1 + email automatica)
- Briefing AI giornaliero + Chat AI sui dati del ristorante
- Strumenti operativi: Foodcost, Inventario, Diario, Personale/Turni
- Marketplace servizi (consulenza F&B, studi menù, comparatori)
- PWA mobile installabile (5 sezioni: Oggi, Avvisi, Diario, Turni, Assistente)
- Multi-ristorante, soft-delete fatture, custom tags, controllo prezzi

---

## 2. Stack Tecnologico

| Layer | Tecnologia | Note |
|-------|-----------|------|
| Frontend | Next.js 16.2.6 + Tailwind v4 + shadcn/ui v4 | Vercel, `nuovo.oneflux.it` |
| Frontend legacy | Streamlit | Railway, `app.oneflux.it` (fino Fase 10) |
| Backend API | FastAPI + Uvicorn | 122+ endpoint, Railway, threadpool 100 thread |
| Database | Supabase PostgreSQL 15 | EU Frankfurt, RLS attivo, `service_role_key` |
| Edge Function | Deno / TypeScript | Supabase, `invoicetronic-webhook` |
| AI | OpenAI GPT-4o-mini | Classificazione ($0.15/1M token) + Chat AI |
| Email | Brevo SMTP API v3 | 300 email/giorno (free tier) |
| Auth | Argon2id m=65536 | Cookie HttpOnly (Next.js) / Secure+SameSite (Streamlit) |
| SDI | Invoicetronic | Intermediario SDI, codice dest. `7HD37X0` |
| PWA | Service Worker manuale | Network-first, no `next-pwa` (incompatibile Turbopack) |

---

## 3. Architettura

```
Browser → Next.js (Vercel) → /api/* proxy → FastAPI Worker (Railway)
                                                    ↓
Browser → Streamlit (Railway) → worker_client.py → FastAPI Worker
                                                    ↓
                                               Supabase PostgreSQL
                                               OpenAI GPT-4o-mini
                                               Brevo SMTP

SDI → Invoicetronic → webhook → Supabase Edge Function → fatture_queue
                                                               ↓
                                               Railway queue-worker (24/7, 15s loop)
```

Entrambi i frontend puntano allo **stesso database Supabase** — un cliente che carica su Streamlit vede i dati immediatamente anche su Next.js.

---

## 4. Struttura del Codice

```
ONEFLUX/
├── apps/web/           # Next.js (Vercel)
│   ├── src/app/
│   │   ├── (app)/      # Pagine autenticate (dashboard, fatture, margini, ecc.)
│   │   ├── (legal)/    # /privacy + /termini (pubbliche)
│   │   ├── (mobile)/   # PWA /m (5 sezioni mobile)
│   │   └── api/        # 100+ proxy routes → FastAPI Worker
│   └── public/         # manifest.json, sw.js, icone PWA
├── app.py              # Entry point Streamlit (legacy)
├── pages/              # Pagine Streamlit multi-page
├── services/           # Business logic (condiviso da entrambi i frontend)
│   ├── fastapi_worker.py           # 122+ endpoint REST
│   ├── ai_service.py               # Classificazione AI + memoria 3 livelli
│   ├── auth_service.py             # Login, reset, rate limiting
│   ├── invoice_service.py          # Parsing XML/P7M/PDF/Vision
│   ├── db_service.py               # Query Supabase + cache
│   ├── margine_service.py          # Calcoli MOL
│   ├── upload_handler.py           # Upload + routing confidenza
│   ├── daily_briefing_service.py   # Briefing AI giornaliero
│   ├── notification_service.py     # Notifiche in-app
│   ├── tag_analytics_service.py    # Analytics custom tags
│   └── tag_suggestion_service.py   # Suggerimenti tag automatici
├── worker/             # Coda Invoicetronic (Railway, loop 15s)
├── supabase/functions/ # Edge Function Deno (webhook SDI)
├── config/             # constants.py (31 categorie, 600+ keyword)
├── migrations/         # SQL legacy (001→068) + timestamp-based Supabase
└── tests/              # 760+ test pytest
```

---

## 5. Sezioni dell'Applicazione

| Sezione | Route | Funzionalità chiave |
|---------|-------|---------------------|
| Home AI | `/dashboard` | Briefing AI + Salute gestione + Conto economico + Chat AI |
| Analisi Fatture | `/analisi-fatture` | Upload, classificazione, pivot categorie/fornitori |
| Gestione Fatture | `/scadenziario` | Agenda scadenze, calendario, cestino integrato |
| Ricavi e Margini | `/margini` | MOL, centri produzione, import ricavi XLS |
| Prezzi | `/prezzi` | Variazioni, sconti/omaggi, note credito |
| Analisi e Tag | `/analisi-e-tag` | Custom tags, trend prezzi, analisi fornitori |
| Strumenti | `/workspace` | Foodcost, Inventario, Diario, Personale/Turni |
| Servizi | `/assistenza` | Marketplace + Chat AI (widget flottante sulla Home) |
| Notifiche | `/notifiche` | Inbox con filtri, badge unificato |
| Impostazioni | `/impostazioni` | Account, piano, contatori, cambio password |
| Admin | `/admin` | Clienti, Qualità AI, Sistema/Salute, Richieste servizi |
| Privacy / Termini | `/privacy`, `/termini` | Pagine legali pubbliche (senza login) |
| Mobile | `/m` | PWA 5 sezioni (Oggi/Avvisi/Diario/Turni/Assistente) |

---

## 6. Pipeline Classificazione AI

**5 livelli di priorità:**
1. Memoria Admin (`classificazioni_manuali`) — globale, massima priorità
2. Memoria Locale (`prodotti_utente`) — per singolo cliente
3. Memoria Globale (`prodotti_master`) — per tutti i clienti
4. Dizionario keyword (`constants.py`) — 600+ regole deterministiche
5. GPT-4o-mini — batch 50 articoli, retry esponenziale

**Routing confidenza (sull'ingest):**
- `altissima / alta` → `needs_review=False`, nessuna coda
- `media / bassa` → `needs_review=True`, coda admin

**31 categorie:** 25 F&B + 1 Materiale + 3 Spese Operative + speciali (Diciture solo €0)

**Vincolo DB:** `categoria = 'Da Clasificare'` è VIETATA (constraint). Fallback: `"SERVIZI E CONSULENZE"`.

**Cache in-memory:** thread-safe (`threading.Lock()`), caricamento lazy, invalidazione cross-process via `cache_version` + trigger DB.

> Dettaglio completo: [AI_PIPELINE.md](AI_PIPELINE.md)

---

## 7. Autenticazione e Sicurezza

| Elemento | Valore |
|----------|--------|
| Password hashing | Argon2id m=65536, parametri default `argon2-cffi` (OWASP) |
| Sessione | `secrets.token_urlsafe(32)`, 30 giorni, auto-logout 8h inattività |
| Cookie Next.js | HttpOnly + Secure + SameSite=Lax |
| Cookie Streamlit | Secure + SameSite=Strict (no HttpOnly — limitazione libreria) |
| Cookie impersonazione | HttpOnly, flag tecnico (no PII in chiaro in JS), TTL 30 min |
| Rate limiting login | 5 tentativi → 15 min lockout (persistente su tabella `login_attempts`) |
| Rate limiting reset | 1 richiesta / 5 min (in-memory thread-safe) |
| Password policy | Min 10 char, 3/4 complessità, blacklist 24+ password comuni |
| Reset token | `secrets.token_urlsafe(32)`, scade in 15 min, verifica HMAC constant-time |
| Admin guard (FastAPI) | Worker key + bearer token → utente → `is_admin` |
| XXE | `defusedxml` su parsing XML |
| SSRF | Whitelist host solo `*.invoicetronic.com/.it` su HTTPS |
| Upload | Magic bytes validation (PDF/XML/P7M), size limits |

> Dettaglio completo: [SICUREZZA_GDPR.md](SICUREZZA_GDPR.md)

---

## 8. Database (tabelle principali)

| Tabella | Scopo |
|---------|-------|
| `users` | Utenti: email, password_hash, session_token, nome_referente, `pagine_abilitate` |
| `ristoranti` | Locali: user_id, nome, P.IVA, attivo |
| `fatture` | Righe fattura: descrizione, prezzo, categoria, `deleted_at`, `needs_review` |
| `prodotti_master` | Memoria globale AI |
| `prodotti_utente` | Memoria locale per cliente |
| `classificazioni_manuali` | Override admin + flag `is_dicitura` |
| `margini_mensili` | MOL mensile + centri produzione |
| `ricavi_giornalieri` | Ricavi day-by-day (import gestionale) |
| `fatture_queue` | Buffer webhook Invoicetronic |
| `login_attempts` | Rate limiting persistente |
| `ai_usage_events` | Ledger costi OpenAI |
| `ai_review_log` | Audit log azioni AI admin (con undo) |
| `diario_eventi` | Calendario eventi ristorante |
| `turni_personale` | Turni con ore, extra, costo orario |
| `inventario_voci` | Giacenze (valore calcolato GENERATED ALWAYS AS) |
| `chat_usage_log` | Domande chat AI per piano/giorno |
| `marketplace_leads` | Lead da form Servizi |
| `custom_tags` + `custom_tag_prodotti` | Tag personalizzati ristorante |
| `assistant_preferences` | Config assistente AI per ristorante |
| `daily_briefing_state` | Cache briefing giornaliero |

**Migration:** 68 file legacy (001→068) + file timestamp-based Supabase.

> Schema completo con colonne: [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)

---

## 9. Calcolo MOL

| Voce | Fonte |
|------|-------|
| Fatturato Netto | (IVA10/1.10) + (IVA22/1.22) + altri_ricavi |
| Costi F&B | `costi_fb_auto` (fatture) + `altri_costi_fb` (manuale) |
| Costo Personale | `costo_dipendenti` + `costo_personale_extra` (da turni o manuale) |
| **MOL** | **Fatturato Netto − F&B − Spese − Personale** |

**Soglie:** Food Cost 🟢<28% 🟡28-33% 🟠33-38% 🔴>38% | MOL 🟢>20% 🟡12-20% 🟠5-12% 🔴<5%

---

## 10. Integrazione Invoicetronic

**Flusso:** SDI → Invoicetronic → POST webhook HMAC-SHA256 → Supabase Edge Function (Deno) → `fatture_queue` → Railway queue-worker (loop 15s) → parsing + AI → mark done + purge XML (24h GDPR)

**Codice SDI:** `7HD37X0` | **Anti-replay:** 5 minuti | **Lock atomico:** `SELECT FOR UPDATE SKIP LOCKED`

---

## 11. Infrastruttura

| Servizio | Piano | Uso |
|---------|-------|-----|
| Vercel | Free → Pro €20 quando serve | Next.js `nuovo.oneflux.it` |
| Railway `ingenious-fascination` | €5/mese | Streamlit + FastAPI Worker + queue-worker |
| Supabase | Free → Pro €25 solo se problemi reali | Database + Edge Functions |
| Brevo | Free tier | Email transazionali |
| GitHub Actions | Free | Uptime check 5min + fallback worker manuale |

> Dettaglio deploy e secrets: [DEPLOY_INFRASTRUTTURA.md](DEPLOY_INFRASTRUTTURA.md)

---

## 12. Testing

- **760+ test pytest** — tutti PASSED
- Mock completi per Supabase e OpenAI (nessun servizio esterno toccato)
- Next.js: `tsc --noEmit` + ESLint + `next build`
- OpenAPI drift check: `python scripts/export_openapi.py --check-drift`

```bash
pytest tests/ -v --tb=short
python scripts/export_openapi.py --check-drift
```

---

## 13. Compliance GDPR

**Titolare:** Recoma System S.r.l. (P.IVA IT09599210961) | Referente: Mattia D'Avolio — md@oneflux.it

- Privacy & Cookie Policy v4.0 — `/privacy` (Next.js)
- Cookie tecnici solo → no cookie-wall (Provvedimento Garante 10/06/2021)
- Consenso esplicito all'onboarding (`privacy_accepted_at` scritto solo se checkbox spuntato)
- Cookie impersonazione HttpOnly senza PII (email derivata server-side)
- Diritto all'oblio: eliminazione cascata su 16+ tabelle
- Portabilità: export JSON Art.20 da Impostazioni
- XML Invoicetronic purge GDPR dopo 24h
- Retention fatture: soft-delete 30gg + auto-eliminazione > 2 anni

> Dettaglio completo: [SICUREZZA_GDPR.md](SICUREZZA_GDPR.md)

---

## 14. Stato Migrazione Next.js

| Fase | Stato |
|------|-------|
| 0–1b | ✅ Scaffold + design system + Vercel |
| 2 | ✅ Auth (login/logout/reset/onboarding) |
| 3 | ✅ Home AI + Notifiche v2 |
| 4 | ✅ Analisi Fatture + Gestione Fatture + Cestino |
| 5 | ✅ Ricavi e Margini + Prezzi |
| 6 | ✅ Strumenti (Foodcost + Inventario + Diario + Personale) |
| 7 | ✅ Admin Panel completo + Qualità AI + Routing confidenza |
| 8 | ✅ Chat AI + Marketplace + Account |
| **PWA** | ✅ Mobile /m (5 sezioni, installabile) |
| **Privacy** | ✅ v4.0 con Recoma, consenso reale, cookie notice |
| 9 | ⏳ Test come cliente reale + fix bug |
| 10 | ⏳ Switch DNS (`app.oneflux.it` → Next.js) |
| 11 | ⏳ Spegnimento Streamlit |

> Dettaglio fasi e changelog: [MIGRAZIONE_NEXTJS.md](MIGRAZIONE_NEXTJS.md)

---

## 15. Limiti Tecnici

| Limite | Valore |
|--------|--------|
| Upload | 100 file / 200 MB totale / 50 MB per P7M |
| AI classificazione/giorno | 1.000 per ristorante |
| Chat AI domande/giorno | 0 (free) / 10 (base) / 20 (plus) / 30 (pro) |
| Sessione cookie | 30 giorni |
| Inattività auto-logout | 8 ore |
| Lockout login | 15 min dopo 5 tentativi |
| XML purge GDPR | 24 ore |
| Finestra notifiche scadute | 90 giorni |

---

*Sintesi v6.0 — 5 Giugno 2026 | Per dettagli tecnici: [DOCUMENTAZIONE_COMPLETA.md](DOCUMENTAZIONE_COMPLETA.md)*
