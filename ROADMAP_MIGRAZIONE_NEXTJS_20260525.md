# ROADMAP OPERATIVA — MIGRAZIONE ONEFLUX a Next.js 14

**Data:** 25 maggio 2026  
**Documento collegato:** `AUDIT_MIGRAZIONE_NEXTJS_20260525.md`  
**Scope:** piano esecutivo dettagliato per la migrazione frontend da Streamlit a Next.js 14, mantenendo backend FastAPI, Supabase, worker Python e Edge Functions invariati.

---

## INDICE

- Convenzioni del documento
- Decisioni architetturali bloccanti
- FASE 0 — Pre-flight (settimana 0)
- FASE 1 — Foundation Next.js (settimane 1–2)
- FASE 2 — Auth e Sidebar (settimane 3–4)
- FASE 3 — Dashboard e Upload (settimane 5–6)
- FASE 4 — Notifiche, Scadenziario, Cestino (settimana 7)
- FASE 5 — Controllo Prezzi e Calcolo Margine (settimane 8–9)
- FASE 6 — Analisi Personalizzata e Foodcost (settimane 10–11)
- FASE 7 — Admin Panel (settimana 12)
- FASE 8 — Hardening, A/B test, accessibility (settimana 13)
- FASE 9 — Cutover graduale (settimane 14–15)
- FASE 10 — Spegnimento Streamlit e cleanup (settimana 16)
- FASE 11 — Estensioni post-MVP (Fase 2: PWA + agente AI + Supabase Auth)
- Matrice rischi e mitigazioni per fase
- Checklist di Definition of Done globale

---

## CONVENZIONI DEL DOCUMENTO

Ogni fase contiene:

- **Obiettivo:** cosa deve esistere alla fine della fase
- **Pre-requisiti:** cosa deve essere completato prima
- **Deliverable:** file, branch, endpoint, documenti
- **Step operativi:** sequenza ordinata di task
- **Criterio di done:** condizioni verificabili
- **Rischi specifici:** elementi su cui prestare attenzione
- **Effort stimato:** giorni-persona

Le stime sono indicative e vanno riviste a fine di ogni fase.

---

## DECISIONI ARCHITETTURALI BLOCCANTI

Queste decisioni vanno congelate prima di iniziare la Fase 1. Sono già state istruite nell'audit.

| Decisione | Scelta | Razionale |
|---|---|---|
| Repo layout | Monorepo `pnpm` workspaces: `apps/web` (Next), `apps/api` (FastAPI esistente), `apps/worker` (Python invariato), `packages/shared` (tipi + costanti) | Tipi condivisi via OpenAPI, single source of truth |
| Auth in Fase 1 | Custom (Argon2 + session_token), cookie HttpOnly su dominio Next | Zero impatto utenti; sicurezza migliora vs Streamlit |
| Auth in Fase 2 | Valutazione Supabase Auth sfruttando `users.auth_uid` (mig 078) | RLS nativa, rotazione token, MFA possibile |
| UI kit | ShadcnUI + Radix + Tailwind | Full ownership componenti, dark mode banale, requisito "personalizzabile" |
| State server | TanStack Query v5 | Invalidation per key fine-grained, replica `cache_version` |
| State UI | Zustand | Leggero, no provider hell, debug DevTools |
| Form | react-hook-form + Zod | Validazione tipizzata, performante |
| Charts | Recharts (Plotly come fallback se necessario) | React-first, tree-shakable |
| i18n | next-intl | App Router native, type-safe |
| Hosting frontend | Vercel | ISR, edge middleware, observability |
| Hosting backend/worker | Railway (invariato) | Continuità |
| Strategia cutover | Feature flag per tenant (`users.frontend_preferred`) | Rollback istantaneo, rischio zero |
| Tipi condivisi Python ↔ TS | OpenAPI generato da FastAPI + `openapi-typescript` | Elimina drift contratto |

---

## FASE 0 — PRE-FLIGHT (settimana 0)

### Obiettivo

Stabilizzare il codebase Streamlit attuale e preparare il terreno per il nuovo frontend, senza introdurre debito tecnico nel branch Next.

### Pre-requisiti

- Accesso completo al repo Git
- Accesso a Railway, Supabase Dashboard, Vercel account
- Approvazione formale del piano da parte del team

### Deliverable

- Branch `refactor/fase-1-architettura` chiuso o mergiato in `main`
- Fix `ADMIN_EMAILS` normalization in `config/constants.py`
- Helper centralizzato `_filter_active_rows` in `services/db_service.py`
- OpenAPI schema esportato da FastAPI e committato in `openapi/openapi.json`
- Documento `DECISIONI_ARCHITETTURALI.md` firmato

### Step operativi

1. **Audit branch pendenti**
   - Verificare lo stato di `refactor/fase-1-architettura`
   - Decidere se merge, abort o continuare
   - Output: branch attivi = solo `main` + nuovi branch dedicati

2. **Fix `ADMIN_EMAILS` normalization**
   - Modificare `config/constants.py` per applicare `.strip().lower()` su tutti gli elementi
   - Verificare che tutti i call site usino già `.strip().lower()` (memoria utente conferma sì)
   - Test: login admin + impersonazione + sidebar admin button visibility
   - Effort: 0.5 h

3. **Centralizzazione filtro soft-delete**
   - Creare helper `_filter_active(query)` in `services/db_service.py`
   - Identificare tutte le query che leggono `fatture` senza filtro `deleted_at IS NULL`
   - Adottare l'helper in tutti i call site
   - Test di regressione: dashboard, export Excel, scadenziario
   - Effort: 1 giorno

4. **Export OpenAPI schema FastAPI**
   - Aggiungere endpoint `GET /openapi.json` (già nativo FastAPI)
   - Script `scripts/export_openapi.py` che salva `openapi/openapi.json`
   - Aggiungere alla pipeline CI come step obbligatorio (fail su drift)
   - Effort: 0.5 giorno

5. **Setup monorepo (preparatorio, non attivo)**
   - Decidere se introdurre `pnpm` workspaces subito o dopo Fase 1
   - Bozza struttura `apps/` e `packages/`
   - Effort: 0.5 giorno

### Criterio di done

- [ ] Nessun branch attivo oltre `main` e i nuovi branch dedicati
- [ ] Test smoke su login admin verde
- [ ] `openapi.json` presente nel repo e aggiornato
- [ ] Audit `deleted_at` documentato

### Rischi specifici

- Branch pendente con conflitti: prevedere mezza giornata in più per rebase manuale
- Helper centralizzato che cambia query semantica: avere snapshot DB pre-fix per confronto

### Effort stimato

**5 giorni-persona** (1 dev senior).

---

## FASE 1 — FOUNDATION NEXT.JS (settimane 1–2)

### Obiettivo

Avere uno scheletro Next.js funzionante con design system, layout di base, dark mode, i18n, deploy su Vercel staging.

### Pre-requisiti

- Fase 0 completata
- Decisioni architetturali firmate

### Deliverable

- Branch `feat/next-frontend` creato e attivo
- `apps/web` scaffold Next.js 14 App Router + TypeScript strict
- Tailwind + ShadcnUI configurati con design tokens ONEFLUX
- next-intl con dizionari `it.json` e `en.json` (placeholder)
- Layout root con header, sidebar placeholder, theme switcher
- Deploy Vercel preview funzionante (URL pubblico staging)
- Lint + Prettier + Husky pre-commit attivi

### Step operativi

1. **Scaffold monorepo**
   - `pnpm init` + workspaces
   - `apps/web` con `create-next-app@latest --typescript --app --tailwind --eslint --src-dir`
   - Spostare `services/`, `worker/`, `migrations/` sotto `apps/api` (oppure mantenere root come ora con symlink)
   - Effort: 1 giorno

2. **Design system base**
   - Installare ShadcnUI: `pnpm dlx shadcn@latest init`
   - Componenti iniziali: Button, Input, Card, Dialog, DropdownMenu, Tabs, Toast, Form
   - Estrarre design tokens da `static/design_tokens.css` esistente
   - Configurare Tailwind con palette ONEFLUX (colori brand, dark mode)
   - Effort: 1.5 giorni

3. **Dark mode**
   - `next-themes` per gestione client + cookie
   - Toggle visibile in header
   - Test contrasto WCAG AA su tutti i token
   - Effort: 0.5 giorno

4. **i18n setup**
   - `next-intl` con route group `[locale]`
   - Dizionari `it.json` (riempire al volo durante le pagine) e `en.json` (placeholder)
   - Helper `useTranslations()` standard
   - Effort: 0.5 giorno

5. **Layout root + navigazione skeleton**
   - `app/[locale]/layout.tsx` con header + sidebar slot
   - Sidebar con voci hard-coded (Dashboard, Fatture, Margine, Prezzi, Tag, Notifiche, Account, Admin)
   - Theme switcher in header
   - Effort: 1 giorno

6. **Deploy Vercel staging**
   - Connettere repo a Vercel
   - Configurare env vars: `NEXT_PUBLIC_API_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY` (mai `service_role`)
   - Domain preview: `oneflux-next.vercel.app`
   - Effort: 0.5 giorno

7. **Pipeline qualità**
   - ESLint config (next-recommended + import sort)
   - Prettier
   - Husky pre-commit con lint-staged
   - GitHub Actions per type-check + build + lint su PR
   - Effort: 0.5 giorno

8. **Tipi condivisi**
   - `packages/shared/types.ts` generato da `openapi-typescript apps/api/openapi/openapi.json`
   - Script `pnpm gen:types` nel root
   - Effort: 0.5 giorno

### Criterio di done

- [ ] `pnpm dev` apre Next.js su `localhost:3000`
- [ ] Vercel preview accessibile pubblicamente
- [ ] Dark mode toggle funzionante
- [ ] Cambio lingua it→en (placeholder)
- [ ] Tipi TS generati da OpenAPI senza errori
- [ ] CI verde su PR

### Rischi specifici

- Conflitti tra struttura attuale e monorepo: testare in branch isolato
- ShadcnUI versioning: bloccare versione esatta
- Design token mismatch tra Streamlit CSS e Tailwind: validare visivamente con designer

### Effort stimato

**6 giorni-persona** (1–2 dev).

---

## FASE 2 — AUTH E SIDEBAR (settimane 3–4)

### Obiettivo

Implementare login, logout, reset password, session refresh, impersonazione admin, sidebar reale con multi-ristorante switcher e gating pagine.

### Pre-requisiti

- Fase 1 completata
- Endpoint FastAPI auth esposti: `/api/auth/login`, `/api/auth/logout`, `/api/auth/reset`, `/api/auth/verify-reset`, `/api/auth/session`

### Deliverable

- Route `[locale]/login` con form (email + password + reset password link)
- Route `[locale]/reset-password` con flusso token
- API route Next `/api/auth/*` come proxy a FastAPI con cookie HttpOnly setting
- Middleware Next.js per protezione route private
- Sidebar reale con voci dinamiche basate su `pagine_abilitate`
- Switcher multi-ristorante in header
- Banner impersonazione admin

### Step operativi

1. **Endpoint FastAPI auth (lato backend)**
   - Estendere `services/fastapi_worker.py` o creare `apps/api/auth_router.py`
   - Implementare `POST /api/auth/login` che riusa `auth_service.verifica_credenziali`
   - `POST /api/auth/logout`, `POST /api/auth/reset`, `POST /api/auth/verify-reset`
   - `GET /api/auth/session` che valida cookie session_token e ritorna user payload
   - `POST /api/auth/impersonate` (admin only)
   - Tutti gli endpoint settano `Set-Cookie: session_token=...; HttpOnly; SameSite=Strict; Secure; Max-Age=2592000`
   - Effort: 3 giorni

2. **Middleware Next.js auth guard**
   - `apps/web/middleware.ts` che intercetta tutte le route private
   - Validazione cookie → chiamata a `/api/auth/session` lato server
   - Redirect a `/login` se non autenticato
   - Effort: 1 giorno

3. **Pagina login**
   - Form con react-hook-form + Zod
   - Errore inline (credenziali, rate-limit, account disattivato)
   - Link reset password
   - "Ricordami" (default: 30 giorni)
   - Test E2E Playwright: login OK, login KO, rate-limit
   - Effort: 1.5 giorni

4. **Reset password flow**
   - `/forgot-password` → richiesta email
   - Mail inviata via Brevo (riusa `services/email_service.py`)
   - `/reset-password?token=...` con form nuova password (Zod compliance: 10 char, 3/4 classi)
   - Effort: 1 giorno

5. **Sidebar dinamica**
   - Server Component che legge `pagine_abilitate` da `/api/users/me`
   - Voci condizionali (`workspace`, `analisi_personalizzata`)
   - Active state via `usePathname()`
   - Effort: 1 giorno

6. **Switcher multi-ristorante**
   - Dropdown header con lista ristoranti utente
   - Cambio ristorante chiama `PATCH /api/users/me { ultimo_ristorante_id }` + `router.refresh()`
   - Invalidare React Query cache su cambio
   - Effort: 1 giorno

7. **Impersonazione admin**
   - In sidebar admin: pulsante "Impersona" per ogni cliente
   - Setta cookie `impersonation_user_id` (TTL 30 min)
   - Banner persistente in alto "Stai impersonando X — Termina"
   - Pulsante termina → `POST /api/auth/end-impersonation`
   - Test: timeout automatico, ripristino admin session
   - Effort: 2 giorni

### Criterio di done

- [ ] Login + logout funzionante con cookie HttpOnly
- [ ] Reset password end-to-end (email ricevuta + token validato)
- [ ] Middleware redirect funziona su tutte le route private
- [ ] Sidebar mostra solo pagine abilitate per utente
- [ ] Switcher ristorante cambia tenant senza ricaricare pagina
- [ ] Impersonazione admin: banner visibile, timeout 30 min server-side
- [ ] Test E2E Playwright copre tutti i flow

### Rischi specifici

- Cookie HttpOnly su dominio diverso da API: configurare CORS e `credentials: 'include'`
- Race condition impersonazione: usare timestamp Postgres come single source of truth
- Rate-limit login: testare che il blocco persista anche cambiando IP/browser

### Effort stimato

**11 giorni-persona** (2 dev: 1 frontend, 1 backend).

---

## FASE 3 — DASHBOARD E UPLOAD (settimane 5–6)

### Obiettivo

Dashboard principale funzionante (KPI + grafici) e upload fatture XML/P7M/PDF con drag&drop e feedback realtime.

### Pre-requisiti

- Fase 2 completata
- Endpoint `/api/fatture`, `/api/dashboard/stats`, `/api/upload`, `/api/cache-version`

### Deliverable

- Pagina `[locale]/dashboard` con KPI cards, grafico spesa mensile (Recharts), tabella ultime fatture
- Pagina `[locale]/upload` con drag&drop multiplo
- Notifiche realtime su upload completato (polling 30s su `cache_version`)
- Errori upload mostrati con messaggi specifici (duplicato, formato, trial limit)

### Step operativi

1. **Endpoint backend dashboard**
   - `GET /api/dashboard/stats` ritorna {totale_fatture, totale_righe, ultimo_upload, spesa_mese, top_categorie, top_fornitori}
   - Riusa `services/db_service.get_fatture_stats`
   - Cache HTTP `Cache-Control: max-age=60, must-revalidate`
   - Effort: 1.5 giorni

2. **Pagina dashboard**
   - Server Component fetch iniziale `/api/dashboard/stats`
   - KPI cards con ShadcnUI Card
   - Grafico spesa mensile (Recharts AreaChart)
   - Tabella top 10 fatture recenti (TanStack Table)
   - Cache version polling (30s) per invalidare React Query
   - Effort: 2 giorni

3. **Endpoint upload backend**
   - `POST /api/upload` accetta multipart (max 50 file)
   - Per ogni file: validazione mime, INSERT in `fatture_queue` (status=pending)
   - Acquisisce lock `upload_locks` per ristorante_id
   - Ritorna {upload_id, accepted_files, rejected_files: [{name, reason}]}
   - Effort: 2 giorni

4. **Componente Upload Next.js**
   - react-dropzone con accept `.xml,.p7m,.pdf,.jpg,.png`
   - Limite client 200 MB totali, 50 file
   - Disclaimer P.IVA visibile
   - Progress bar per file
   - Su success: toast + invalidate dashboard cache
   - Effort: 2 giorni

5. **Polling stato upload**
   - Dopo upload, polling `GET /api/upload/{upload_id}/status` ogni 5s
   - Mostra contatore "X / Y processati"
   - Quando complete: notifica + scroll a tabella fatture recenti
   - Effort: 1 giorno

6. **Anomaly e classificazione async**
   - Worker (esistente, invariato) processa coda
   - Cliente vede aggiornamenti via polling `cache_version`
   - Notifiche generate via `notification_inbox_service` visibili in sidebar (Fase 4)
   - Effort: 0 (backend invariato)

### Criterio di done

- [ ] Dashboard carica in < 1.5s (TTFB + paint)
- [ ] Upload 10 XML in parallelo termina in < 30s end-to-end
- [ ] Errori specifici mostrati (duplicato, trial, formato)
- [ ] Cache_version polling funziona (dashboard si aggiorna senza F5)
- [ ] Lock upload impedisce upload concorrenti sullo stesso ristorante

### Rischi specifici

- File 200 MB su Vercel: limite request body 4.5 MB su Serverless Functions → usare `Edge Function` o upload diretto a Supabase Storage con pre-signed URL
- Polling troppo aggressivo: rate-limit lato API per evitare flood

### Effort stimato

**9 giorni-persona** (2 dev).

---

## FASE 4 — NOTIFICHE, SCADENZIARIO, CESTINO (settimana 7)

### Obiettivo

Migrare pagina `5_notifiche_e_gestione.py` con 3 tab: notifiche, scadenziario, gestione fatture.

### Pre-requisiti

- Fase 3 completata
- Endpoint `/api/notifiche`, `/api/fatture-documenti`, `/api/fatture/cestino`

### Deliverable

- Pagina `[locale]/notifiche` con 3 tab
- Preview fattura come modale (React component)
- Soft-delete + ripristino + svuota cestino
- Segna pagata + aggiorna competenza

### Step operativi

1. **Endpoint backend**
   - Riusa servizi esistenti (`documenti_service`, `notification_inbox_service`, `db_service`)
   - Effort: 2 giorni

2. **Tab Notifiche**
   - Lista notifiche inbox con dismiss singola/multipla
   - Badge non lette
   - Refresh ogni 60s (background polling)
   - Effort: 1 giorno

3. **Tab Scadenziario**
   - TanStack Table con filtri (pagata/non pagata, scadenza)
   - Toggle "segna pagata" inline con optimistic update
   - Esporta in Excel
   - Effort: 1.5 giorni

4. **Tab Gestione Fatture**
   - Lista documenti con preview modale (no iframe — React component)
   - Soft-delete con conferma
   - Cestino: ripristino + svuota
   - Effort: 1.5 giorni

### Criterio di done

- [ ] Tutte le azioni hanno feedback ottimistico
- [ ] Preview fattura visibile in < 500ms
- [ ] Cestino: file ripristinati ricompaiono in lista immediatamente

### Rischi specifici

- Preview HTML legacy con CSS inline → portare a componente React tipizzato
- Mismatch cache tra tab → invalidare gruppo `['fatture']` su qualsiasi mutation

### Effort stimato

**6 giorni-persona**.

---

## FASE 5 — CONTROLLO PREZZI E CALCOLO MARGINE (settimane 8–9)

### Obiettivo

Migrare pagine `3_controllo_prezzi.py` e `1_calcolo_margine.py` con grafici e form complessi.

### Pre-requisiti

- Fase 4 completata
- Endpoint `/api/alert-prezzi`, `/api/margini/{anno}`, `/api/fatturato-centri`

### Deliverable

- Pagina `[locale]/prezzi` con alert table + grafico trend prezzo
- Pagina `[locale]/margine` con tabella MOL + form fatturato centri

### Step operativi

#### Controllo Prezzi (5 giorni)

1. Endpoint `GET /api/alert-prezzi` con filtri (periodo, soglia, prodotto)
2. Endpoint `GET /api/sconti-omaggi` per il riepilogo
3. UI con 3 tab (Variazioni, Sconti, Note di Credito)
4. Soglia alert salvabile per utente (`users.price_alert_threshold`)
5. Grafico Recharts con annotazioni + tooltip custom

#### Calcolo Margine (5 giorni)

1. Endpoint `GET /api/margini/{anno}` ritorna tutti i mesi
2. Endpoint `POST /api/margini` per salvataggio
3. Endpoint `POST /api/fatturato-centri` per split
4. UI con 2 tab (Calcolo, Analisi Avanzate)
5. Tabella trasposta (voci × mesi) con TanStack Table
6. Form split centri con validazione live (€ / %)

### Criterio di done

- [ ] Alert calcolati identici tra Streamlit e Next (test parity su 10 ristoranti)
- [ ] Salvataggio margine atomico (nessun mese parziale salvato)
- [ ] Export Excel funziona (server-side generation)

### Rischi specifici

- Calcolo MOL: numerose regole di business — coprire con test unitari Python
- Pivot complesso: TanStack Table custom column groups

### Effort stimato

**10 giorni-persona**.

---

## FASE 6 — ANALISI PERSONALIZZATA E FOODCOST (settimane 10–11)

### Obiettivo

Migrare `4_analisi_personalizzata.py` e `2_foodcost.py` (la pagina più complessa).

### Pre-requisiti

- Fase 5 completata
- Endpoint `/api/custom-tags`, `/api/ricette`, `/api/ingredienti`, `/api/note-diario`

### Deliverable

- Pagina `[locale]/tag` con CRUD tag custom + analisi
- Pagina `[locale]/foodcost` con 4 tab: Analisi, Lab Ricette, Diario, Export

### Step operativi

#### Analisi Personalizzata (5 giorni)

1. Endpoint CRUD `custom_tags` + `custom_tag_associazioni`
2. UI gestione tag (create, edit emoji+colore, delete con conferma)
3. UI associazione descrizioni (search + multiselect)
4. Tab analisi: KPI cards + grafico trend + tabella fornitori
5. Orfani check + warning

#### Foodcost (8 giorni)

1. Endpoint `GET /api/ingredienti/dropdown` che fa il merge di 3 fonti
2. Endpoint CRUD `ricette` + `ingredienti_ricetta` + `ingredienti_workspace`
3. UI Tab Analisi: riepilogo costo/margine per ricetta
4. UI Tab Lab: form crea/edit ricetta con ingredienti multipli
5. UI Crea Ingrediente Manuale (espandibile)
6. UI Lista Ingredienti Workspace con edit inline
7. UI Tab Diario: form nota + lista cronologica
8. UI Tab Export: bottone Excel multi-sheet
9. Estrazione grammatura regex (riusa pattern Python lato server)
10. Calcolo foodcost lato server (`POST /api/foodcost/calcola`)

### Criterio di done

- [ ] Foodcost ricetta identico tra Streamlit e Next su 20 ricette test
- [ ] Workspace ingredienti edit inline funziona senza reload
- [ ] Export Excel ha gli stessi sheet di oggi

### Rischi specifici

- Foodcost è la pagina più complessa: prevedere buffer +30%
- Dropdown merge 3 fonti: ottimizzare con `useMemo` + virtualizzazione

### Effort stimato

**13 giorni-persona**.

---

## FASE 7 — ADMIN PANEL (settimana 12)

### Obiettivo

Migrare `admin.py` con i suoi 5 tab.

### Pre-requisiti

- Fase 6 completata
- Tutti gli endpoint `/api/admin/*` esposti

### Deliverable

- Pagina `[locale]/admin` con 5 tab:
  - Gestione Clienti
  - Review Righe €0
  - Memoria AI (globale, per cliente, conflitti, audit)
  - DB Integrity
  - Costi AI

### Step operativi

1. Endpoint backend (riusano logica esistente in `admin.py` ma esposta REST) — 4 giorni
2. Tab Gestione Clienti con TanStack Table + edit modale — 2 giorni
3. Tab Review Righe €0 con bulk action — 1 giorno
4. Tab Memoria AI con sotto-tab — 1.5 giorni
5. Tab DB Integrity con check + fix button — 1 giorno
6. Tab Costi AI con tabella + filtro periodo — 0.5 giorno

### Criterio di done

- [ ] Admin riesce a fare tutto quello che faceva in Streamlit
- [ ] Impersonazione lavora correttamente dal panel
- [ ] DB health check identico

### Effort stimato

**10 giorni-persona**.

---

## FASE 8 — HARDENING, A/B TEST, ACCESSIBILITY (settimana 13)

### Obiettivo

Stabilizzare, ottimizzare performance, fare test A/B parallelo (Streamlit + Next contemporaneamente), accessibility audit.

### Step operativi

1. **Performance**
   - Lighthouse score >= 90 su tutte le pagine
   - Bundle analysis + code splitting
   - Immagini ottimizzate via `next/image`
   - Server Components dove possibile
   - Effort: 2 giorni

2. **Accessibility (WCAG AA)**
   - Audit con axe-core
   - Focus management nei dialog
   - aria-labels su tutti gli interattivi
   - Test screen reader (NVDA)
   - Effort: 1.5 giorni

3. **Security audit**
   - Headers di sicurezza (CSP, HSTS, X-Frame-Options)
   - Test XSS / CSRF
   - Rate-limit verificato su tutti gli endpoint
   - `service_role_key` mai esposta lato client
   - Effort: 1 giorno

4. **A/B parity test**
   - Selezionare 5 tenant pilota
   - Eseguire stesso workflow su Streamlit e Next, confrontare risultati
   - Documentare ogni discrepanza
   - Effort: 2 giorni

5. **Smoke test E2E**
   - Playwright suite con i flussi critici
   - Esecuzione su CI prima di ogni deploy
   - Effort: 1 giorno

6. **Documentazione utente**
   - Guida "Cosa cambia nella nuova interfaccia" (markdown + screenshots)
   - FAQ
   - Effort: 1 giorno

### Criterio di done

- [ ] Lighthouse >= 90 desktop e mobile
- [ ] axe-core zero violazioni critical/serious
- [ ] Parity test 100% su tenant pilota
- [ ] Playwright suite verde

### Effort stimato

**8.5 giorni-persona**.

---

## FASE 9 — CUTOVER GRADUALE (settimane 14–15)

### Obiettivo

Migrare i clienti da Streamlit a Next.js in modo controllato, con rollback istantaneo.

### Pre-requisiti

- Fase 8 completata
- Aggiunta colonna `users.frontend_preferred` con default `'streamlit'`

### Step operativi

1. **Migration DB**
   - `ALTER TABLE users ADD COLUMN frontend_preferred TEXT DEFAULT 'streamlit'`
   - Effort: 0.5 giorno

2. **Reverse proxy / redirect logic**
   - Su `app.oneflux.it`: lookup `frontend_preferred` per email login
   - Se `'next'` → redirect a `next.oneflux.it`
   - Se `'streamlit'` → resta su Streamlit
   - Implementare in middleware Next OR FastAPI gateway
   - Effort: 1 giorno

3. **Rollout 10%**
   - Selezionare 10% clienti meno critici
   - Aggiornare `frontend_preferred = 'next'`
   - Monitoring intensivo per 72h (Sentry, Logflare)
   - Effort: 2 giorni monitoring

4. **Rollout 50%**
   - Dopo settimana stabile, espandere a 50%
   - Monitoring continuo
   - Effort: 2 giorni monitoring

5. **Rollout 100%**
   - Tutti i clienti su Next
   - Streamlit resta attivo in standby per rollback
   - Effort: 1 giorno comunicazione + supporto

### Criterio di done

- [ ] Tasso di errore < 0.1% per 7 giorni consecutivi
- [ ] Zero ticket gravi su funzionalità migrate
- [ ] Tempo medio caricamento dashboard < 1.5s

### Rischi specifici

- Cliente che fa screenshot di Streamlit per supporto: comunicare il cambio in anticipo
- Bookmark vecchi: redirect 301 da vecchi path a nuovi

### Effort stimato

**6.5 giorni-persona** (in 2 settimane di rolling).

---

## FASE 10 — SPEGNIMENTO STREAMLIT E CLEANUP (settimana 16)

### Obiettivo

Disattivare definitivamente Streamlit, rimuovere codice obsoleto, ridurre superficie di manutenzione.

### Pre-requisiti

- 100% clienti su Next.js da almeno 2 settimane
- Zero rollback richiesti

### Step operativi

1. **Spegnimento Streamlit Cloud**
   - Disattivare deployment
   - Mantenere immagine Docker in registry per rollback emergenza
   - Effort: 0.5 giorno

2. **Cleanup codice Streamlit**
   - Rimuovere `app.py`, `pages/`, `components/`, `controllers/`
   - Rimuovere `utils/streamlit_compat.py`, `utils/sidebar_helper.py`, parte di `utils/ui_helpers.py`
   - Rimuovere dipendenze `streamlit`, `extra-streamlit-components` da `requirements.txt`
   - Mantenere `worker/streamlit_stub.py` (utile per testing)
   - Effort: 1.5 giorni

3. **Cleanup services Streamlit-coupled**
   - Rimuovere `@st.cache_data` da `services/db_service.py`, `margine_service.py`, `documenti_service.py`, `notification_inbox_service.py`, `page_setup.py`
   - Rimuovere `st.session_state`, `st.error`, `st.toast` etc. da services
   - Tutti i service diventano puri (input/output)
   - Effort: 2 giorni

4. **DNS update**
   - `app.oneflux.it` punta a Vercel
   - Rimuovere reverse proxy intermedio
   - Effort: 0.5 giorno

5. **Documentazione finale**
   - Aggiornare `README.md` con nuovo stack
   - Aggiornare `AGENTS.md` con convenzioni Next
   - Archive doc Streamlit in `DOCUMENTAZIONE/legacy/`
   - Effort: 0.5 giorno

### Criterio di done

- [ ] Repo non contiene più import `streamlit` (eccetto worker stub)
- [ ] `requirements.txt` snellito
- [ ] Bundle frontend ridotto
- [ ] CI passa senza Streamlit

### Effort stimato

**5 giorni-persona**.

---

## FASE 11 — ESTENSIONI POST-MVP (FASE 2)

Queste fasi sono successive al cutover. Non vincolanti per il go-live.

### 11.1 PWA mobile installabile

- Manifest + service worker
- Subset di pagine: dashboard, fatture, scadenze, push notifications
- Effort stimato: 10 giorni

### 11.2 Agente AI integrato (chat su dati cliente)

- Sidebar globale "Chiedi a ONEFLUX"
- Backend: function calling su `/api/agent/tools/*` (recupero KPI, ricerche fatture, drilldown)
- Stream chat via SSE
- Scope per `ristorante_id`
- Effort stimato: 15 giorni

### 11.3 Migrazione a Supabase Auth

- Backfill `users.auth_uid` (mig 078 già pronta)
- Re-import password come `crypt(password, gen_salt('bf'))` oppure forced reset
- Aggiornare RLS policy per usare `auth.uid()`
- Rimuovere `service_role_key` da molte query backend
- Comunicazione utenti (link reset di massa o login automatico se possibile)
- Effort stimato: 12 giorni

### 11.4 Realtime con Supabase Realtime

- Sostituire polling `cache_version` con channel Realtime
- Update istantaneo dashboard/notifiche quando worker completa job
- Effort stimato: 5 giorni

### 11.5 Multi-language full coverage

- Completare `en.json` con tutte le stringhe
- Aggiungere altre lingue (es, fr, de) se richiesto
- Effort: 8 giorni per lingua

---

## MATRICE RISCHI E MITIGAZIONI PER FASE

| Fase | Top 3 rischi | Mitigazione principale |
|---|---|---|
| 0 | Branch pendente, normalizzazione email, soft-delete | Audit branch + test smoke + snapshot DB pre-fix |
| 1 | Design token mismatch, monorepo broken | Validazione visuale con designer, branch isolato |
| 2 | Cookie cross-domain, race impersonation | CORS + credentials, timestamp Postgres |
| 3 | Limite upload 4.5 MB Vercel, polling flood | Edge Function o pre-signed URL, rate-limit API |
| 4 | Preview HTML legacy, cache mismatch tab | Portare a componente React, invalidate gruppo |
| 5 | Parity calcolo MOL, pivot complesso | Test unit Python + TanStack column groups |
| 6 | Foodcost effort sottostimato | Buffer +30%, isolate complexity |
| 7 | Admin tab eterogenei | TabsRoot stateful + Server Component per tab pesanti |
| 8 | Performance budget non rispettato | Lighthouse CI obbligatorio in PR |
| 9 | Bookmark vecchi, comunicazione | Redirect 301 + email + in-app banner |
| 10 | Cleanup rompe worker | Test smoke worker dopo ogni rimozione |

---

## CHECKLIST DI DEFINITION OF DONE GLOBALE

- [ ] Tutti gli endpoint FastAPI documentati in OpenAPI e tipizzati lato TS
- [ ] Tutti i flussi critici coperti da test E2E Playwright
- [ ] Lighthouse Performance/Accessibility/Best Practices/SEO >= 90 su 5 pagine top
- [ ] Zero `service_role_key` esposta lato client
- [ ] Tutti i cookie sensibili HttpOnly + Secure + SameSite=Strict
- [ ] Soft-delete coerente tra `fatture` e `fatture_documenti`
- [ ] Cache_version polling implementato lato Next
- [ ] Rate-limit verificato su `/api/auth/login`, `/api/upload`, `/api/classify`
- [ ] GDPR: export + delete account funzionanti, log retention 24h XML rispettato
- [ ] Documentazione utente "Cosa cambia" pubblicata
- [ ] Rollback plan testato in staging
- [ ] On-call team formato sul nuovo stack
- [ ] Monitoring (Sentry, Logflare, Vercel Analytics) attivo su tutti gli ambienti
- [ ] Backup Streamlit Docker image disponibile per 60 giorni post-cutover

---

## RIEPILOGO TIMELINE

| Fase | Durata | Effort (gg-persona) | Output principale |
|---|---|---|---|
| 0 — Pre-flight | 1 settimana | 5 | Codebase Streamlit stabilizzato + OpenAPI |
| 1 — Foundation | 2 settimane | 6 | Scheletro Next.js + design system + Vercel staging |
| 2 — Auth e Sidebar | 2 settimane | 11 | Login + middleware + sidebar dinamica |
| 3 — Dashboard e Upload | 2 settimane | 9 | Dashboard + upload drag&drop |
| 4 — Notifiche e Scadenziario | 1 settimana | 6 | Pagina notifiche + scadenziario + cestino |
| 5 — Prezzi e Margine | 2 settimane | 10 | Alert prezzi + calcolo MOL |
| 6 — Tag e Foodcost | 2 settimane | 13 | Analisi personalizzata + foodcost completo |
| 7 — Admin | 1 settimana | 10 | Pannello admin completo |
| 8 — Hardening | 1 settimana | 8.5 | Performance, accessibility, security |
| 9 — Cutover | 2 settimane | 6.5 | Rollout 10% → 50% → 100% |
| 10 — Cleanup | 1 settimana | 5 | Streamlit spento, codice pulito |
| **TOTALE FASE MVP** | **17 settimane** | **~90 gg-persona** | **Migrazione completata** |
| 11.1 PWA | +2 settimane | 10 | Mobile installabile |
| 11.2 Agente AI | +3 settimane | 15 | Chat su dati cliente |
| 11.3 Supabase Auth | +2 settimane | 12 | RLS nativa |
| 11.4 Realtime | +1 settimana | 5 | Polling sostituito da channel |

---

**Fine documento roadmap.**
