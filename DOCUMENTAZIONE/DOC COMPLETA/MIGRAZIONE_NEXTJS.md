# ONEFLUX — Stato Migrazione Next.js

Versione: 6.2 | Aggiornamento: 19 Giugno 2026

Questo documento riassume lo stato della migrazione da Streamlit a Next.js.
Il documento di riferimento primario (con changelog dettagliato) è `ONEFLUX_MASTER.md`.

> ✅ **Migrazione COMPLETATA (switch 8/6).** Streamlit dismesso; la tabella sotto e i
> riferimenti alla coesistenza sono storici.

---

## 1. Situazione Attuale

| Frontend | URL | Stato | Clienti |
|---------|-----|-------|---------|
| Next.js | `app.oneflux.it` (Vercel) | **Unico frontend attivo** | tutti (2 test + 1 operativo) |
| Streamlit | — | Dismesso (8/6) | nessuno |

Il frontend Next.js e il worker FastAPI puntano allo **stesso database Supabase**.

**Stack Next.js:** Next.js 16.2.6 + Tailwind v4 + shadcn/ui v4 + Vercel

---

## 2. Roadmap — Stato Completo

| Fase | Contenuto | Stato | Data |
|------|-----------|-------|------|
| 0 | Cleanup, schema OpenAPI, `_make_cache()` pattern, no Streamlit deps nei service | ✅ | — |
| 1 | Next.js scaffold + Vercel + `nuovo.oneflux.it` online | ✅ | 26/5 |
| 1b | Design system: palette sky `#0ea5e9`, Inter, shadcn completo, sidebar collapsible, style-guide | ✅ | — |
| 2 | Auth login/logout/me + reset password + onboarding primo accesso | ✅ | 30/5 |
| 3 | Home AI (briefing + Salute + conto economico + configuratore) + Notifiche v2 | ✅ | 2/6 |
| 4 | Analisi Fatture + Analisi e Tag + Gestione Fatture + Cestino (widget) | ✅ | 30/5 |
| 5 | Ricavi e Margini + Prezzi + hardening | ✅ | 29/5 |
| 6 | Strumenti: Foodcost + Inventario + Diario + Personale (4 tab) | ✅ | 31/5 |
| 7 | Admin Panel Core + Qualità AI + Sistema/Salute + routing confidenza ingest | ✅ | 30/5 |
| 8 | Chat AI + Marketplace Servizi + Account/Impostazioni | ✅ | 2/6 |
| PWA | Mobile `/m` (5 sezioni, installabile Android/iOS) | ✅ | 2/6 |
| Privacy | Conformità GDPR Next.js: pagine legali, consenso, cookie notice (rev. 25) | ✅ | 2/6 |
| 9 | Test come cliente reale + invito 2 clienti + fix bug | ⏳ | — |
| 10 | Switch DNS `app.oneflux.it` → Next.js | ⏳ | — |
| 11 | Spegnimento Streamlit | ⏳ | — |

---

## 3. Funzionalità Implementate per Sezione

| Sezione | Route | Stato | Note |
|---------|-------|-------|------|
| Login | `/login` | ✅ | Footer legale + "Hai dimenticato la password?" |
| Forgot password | `/forgot-password` | ✅ | Form email → Brevo → link reset |
| Reset password | `/reset-password` | ✅ | Token URL pre-compilato + nuova password |
| Onboarding | `/reset-password?onboarding=1` | ✅ | Testi personalizzati + checkbox privacy |
| Home AI | `/dashboard` | ✅ | Briefing + Salute + Conto economico + Chat AI widget |
| Analisi Fatture | `/analisi-fatture` | ✅ | KPI bar + filtri + 3 tab + upload modal |
| Gestione Fatture | `/scadenziario` | ✅ | Agenda + calendario + KPI + cestino widget |
| Ricavi e Margini | `/margini` | ✅ | Tab Marginalità + Analisi Avanzate |
| Prezzi | `/prezzi` | ✅ | 3 tab: Variazioni + Sconti/Omaggi + NC |
| Analisi e Tag | `/analisi-e-tag` | ✅ | Chip tag + KPI + trend + suggerimenti |
| Agenda | `/agenda` | ✅ | Layer Tutto (vista aggregata) + Appuntamenti + Spese + Personale (flag `agenda`, dal 10/6) |
| Strumenti | `/workspace` | ✅ | 2 tab: Foodcost + Inventario (flag `workspace`; Diario/Spese/Personale migrati in Agenda) |
| Servizi | `/assistenza` | ✅ | 6 servizi + form lead + WhatsApp |
| Notifiche | `/notifiche` | ✅ | Lista + filtri + badge unificato |
| Impostazioni | `/impostazioni` | ✅ | Account + piano + contatori + cambio password |
| Admin Panel | `/admin/*` | ✅ | Clienti + Qualità AI + Sistema + Richieste |
| Privacy | `/privacy` | ✅ | Policy v4.0 con tabella cookie reale |
| Termini | `/termini` | ✅ | ToS con lista provider |
| Mobile PWA | `/m` | ✅ | 5 sezioni installabili |
| Multi-ristorante | — | ⏳ | Dropdown switch ristorante non ancora implementato |
| Report | — | ⏳ | Placeholder scollegato (fuori scope ora) |

---

## 4. Decisioni Architetturali Chiave

### M1 — Coesistenza senza sincronizzazione
Streamlit e Next.js puntano allo stesso Supabase. Nessuna sincronizzazione necessaria — qualsiasi dato scritto da un frontend è immediatamente visibile dall'altro.

### M2 — Servizi Python invariati
`services/*.py` e `worker/*.py` non vengono modificati durante la migrazione Next.js. Il FastAPI worker rimane il backend unico. Zero file Python toccati durante lo sviluppo frontend.

### M3 — Auth: cookie HttpOnly ora
Next.js usa cookie HttpOnly per la sessione, eliminando il limite di Streamlit (`extra-streamlit-components` non supporta HttpOnly). Migrazione a Supabase Auth completo → post-MVP.

### M4 — Upload file: 4.5 MB limite Next.js
Le fatture elettroniche italiane (XML 10–200 KB, P7M max 500 KB, PDF max 4 MB) rientrano nel limite. Nessun pre-signed URL richiesto.

### M5 — Tab Ricavi eliminato
Inserimento ricavi spostato nel tab Marginalità via dialog "Carica ricavi". La voce sidebar "Ricavi e Margini" accorpa entrambe le funzioni.

### M6 — Foodcost → Strumenti → split Agenda/Strumenti (rivisto 10/6)
L'ex pagina "Foodcost" era diventata "Strumenti" (4 tab: Foodcost, Inventario,
Diario, Personale). Dal **10/6** è **divisa in due pagine/voci di sidebar**:
- **Agenda** (`/agenda`, flag `agenda`): contenitore operativo quotidiano. Layer
  via `?layer=`: **Tutto** (vista aggregata read-only di appuntamenti+spese+turni)
  · Appuntamenti · Spese · Personale. Riusa `AgendaView`/`SpeseView`/`PersonaleTab`.
- **Strumenti** (`/workspace`, flag `workspace`): ridotto a **Foodcost + Inventario**.
  Vecchi link `?tab=agenda|spese|personale` rediretti a `/agenda?layer=...` (il
  redirect resta **prima** del guard, così chi ha solo `agenda` non prende 404).

### M7 — Feature flags: nuova tassonomia (agg. 10/6)
Abbandonati i nomi vecchi Streamlit (`calcolo_margine`, ecc.). Chiavi in
`users.pagine_abilitate`: `analisi_fatture`, `prezzi`, `margini`, `analisi_e_tag`,
**`agenda`** (nuovo, 10/6), **`workspace`**, `scadenziario`,
`blocco_anno_precedente`, `blocco_mesi_precedenti`. Il flag `agenda` è **separato**
da `workspace` (migration `20260610140000`: propagato `agenda:true` ai clienti che
avevano `workspace:true`). `pagine_abilitate` può essere un **dict** `{flag: bool}`
o `null` (admin = tutte abilitate); `_normalize_pagine` (worker) lo normalizza.

### M8 — Gating per-pagina: ora ATTIVO (rivisto 10/6) ⚠️ supera la nota precedente
**Prima** Next.js NON faceva gating per-pagina: `pagine_abilitate` nascondeva solo
le voci di sidebar, ma l'URL diretto restava accessibile col flag spento. **Dal
10/6** c'è un guard di route: **`requirePagina(flag)`** in `apps/web/src/lib/page-guard.ts`,
chiamato in cima a ogni `page.tsx` con flag (7 pagine: analisi-fatture, margini,
prezzi, analisi-e-tag, agenda, workspace, scadenziario). Semantica = sidebar:
`pagine_abilitate` null → passa (admin); flag nella lista → passa; altrimenti
**`notFound()` (404)**. Usa `getCurrentSession` (cache()-wrapped → nessuna chiamata
worker extra). Fratello del **gate tool della chat** (`_TOOL_FLAG`, vedi
`CHAT_ASSISTENTE.md` §5.1). I vecchi valori flag Streamlit restano orfani nel DB.

### M9 — Admin: doppio guard di sicurezza
Il pannello admin Next.js ha il guard nel layout (`admin/layout.tsx` → redirect se non admin). Il FastAPI worker ha `_verify_admin` (worker key + bearer token + `is_admin`) su ogni endpoint admin.

### M10 — Middleware Next.js: blacklist invertita
Il middleware protegge tutto tranne le 3 rotte pubbliche (login, forgot-password, reset-password). Prima era una whitelist delle rotte protette → molte rotte reali non erano protette a edge.

### M11 — `getCurrentUser` con `cache()`
Avvolto in `cache()` di React: una sola chiamata `/api/auth/me` per render, anche se il layout app e il layout admin lo chiamano entrambi.

### M12 — FastAPI: async→def (fix performance)
148 endpoint convertiti da `async def` a `def` (FastAPI li instrada sul threadpool AnyIO). Prima erano `async` ma chiamavano codice sincrono e bloccante → serializzava tutte le richieste su un singolo event loop. Risultato: `/health` 9,5s → 0,21s sotto carico.

---

## 5. Elementi Rimossi / Deprecati

| Elemento | Motivo | Stato |
|----------|--------|-------|
| Sidebar voce "Cestino" | Ora widget integrato in Gestione Fatture | ✅ Rimosso |
| Sidebar voce "Report" | Placeholder non necessario | ✅ Rimosso |
| Voce "Account" dropdown footer | Ridondante con Impostazioni | ✅ Rimosso — footer ora solo "Esci" |
| Route `/cestino/page.tsx` | Non più nel menu | ✅ File rimosso |
| Route `/report/page.tsx` | Non più nel menu | ✅ File rimosso |
| Railway service `exemplary-creation` | Non usato | Da eliminare |
| Tab "Integrità DB" admin | Troppi falsi positivi | ✅ Rimosso da `/admin/sistema` |
| Bottone "🧠 Avvia AI" separato | Integrato direttamente nell'upload | ✅ Rimosso da Streamlit |

---

## 6. Prerequisiti Prima di Fare Switch DNS (Fase 10)

**Checklist pre-switch:**
- [ ] Tutte le sezioni funzionanti e testate come cliente reale (Fase 9)
- [x] Reset password + onboarding funzionanti lato Next.js (Brevo verificato 31/5)
- [x] Privacy & Cookie Policy + ToS pubblicati e raggiungibili (rev. 25)
- [x] Consenso privacy esplicito all'onboarding con prova reale (rev. 25)
- [ ] Aggiornare data/versione informativa al cut-over (allineare lista responsabili)
- [ ] Backup DB confermato prima dello switch
- [ ] Clienti avvisati con almeno 1 settimana di anticipo
- [ ] Rollback plan documentato: `old.oneflux.it` → Streamlit (30gg)

**Prerequisiti infrastruttura:**
- [x] `WORKER_WEB_CONCURRENCY=4` impostata su Railway (chiuso 2/6)
- [x] Env var Brevo su Railway (`BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, `BREVO_SENDER_NAME`) — chiuso 31/5

---

## 7. Piano Switch DNS (Fase 10)

**Settimana 1:**
- `app.oneflux.it` → Streamlit (default per tutti)
- `nuovo.oneflux.it` → Next.js (disponibile)
- Uso personale quotidiano per ≥5 giorni come "cliente reale"
- Invito 2 clienti di test a usare `nuovo.oneflux.it` per attività normali

**Settimana 2:**
- Backup completo Supabase (snapshot pre-switch)
- Switch DNS: `app.oneflux.it` → Next.js (Vercel)
- `old.oneflux.it` → Streamlit (backup 30 giorni)
- Avviso clienti con spiegazione + video breve

**Settimana 3:**
- Monitoraggio attivo
- Fix bug critici se emergono
- Dopo 30 giorni senza problemi → Fase 11 (spegnimento Streamlit)

---

## 8. Punti Aperti (Non bloccanti)

| Punto | Note |
|-------|------|
| Multi-ristorante dropdown switch | Non ancora implementato nel frontend Next.js |
| `fattore_kg` UI in Analisi e Tag | Backend supportato, UI rimandata a v2 |
| Confronto multi-tag | Rimandata a v2 |
| Voce "Installa app" nell'HeaderMenu mobile | Per chi ha chiuso il banner di installazione |
| Endpoint `/api/scadenziario/calendario` morto | Aggregazione client-side, endpoint legacy — valutare rimozione |
| Aggiornamento Privacy Policy al cut-over | Aggiornare data/versione + allineare lista responsabili allo stack post-switch |

---

*Migrazione Next.js v6.1 — 10 Giugno 2026*
*Riferimento principale: `ONEFLUX_MASTER.md` (rev. 26)*
