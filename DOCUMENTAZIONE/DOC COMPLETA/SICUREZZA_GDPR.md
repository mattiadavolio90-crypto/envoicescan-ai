# ONEFLUX — Sicurezza e Compliance GDPR

Versione: 6.0 | Aggiornamento: 5 Giugno 2026

---

## 1. Autenticazione

### Flusso login (comune a Streamlit e Next.js)

```
UTENTE
  │
  ├── Cookie session_token presente?
  │   ├── YES → verifica TTL 30 giorni + token nel DB → login automatico
  │   └── NO → form email + password
  │
  └── Form login:
      1. Rate limit check (tabella login_attempts su DB)
      2. Verifica Argon2id hash
      3. Login OK → session_token = secrets.token_urlsafe(32)
      4. Salva token in DB + imposta cookie
      5. Aggiorna last_login
```

### Password Hashing

| Parametro | Valore |
|-----------|--------|
| Algoritmo | Argon2id |
| Memory cost | 65536 KB (64 MB) |
| Time cost / Parallelism | Parametri default `argon2-cffi` (OWASP raccomandato) |
| Migrazione legacy | Auto da SHA256 al primo login |

### Password Policy (GDPR Art.32 + Garante Privacy)

- Lunghezza minima: 10 caratteri
- Complessità: almeno 3/4 tra maiuscola, minuscola, numero, simbolo
- Blacklist: 24+ password comuni (OWASP + varianti italiane: "ristorante", "pizzeria", ecc.)
- No dati personali: email e nome ristorante vietati nella password
- No pattern semplici: sequenze numeriche e caratteri ripetuti bloccati

### Reset Password via Email

```
1. Utente inserisce email
2. Sistema genera:
   - reset_token = secrets.token_urlsafe(32) (256 bit entropia)
   - codice 6 cifre = secrets.randbelow(1000000)
   - Scadenza: 15 minuti
3. Email inviata via Brevo con codice
4. Utente inserisce codice + nuova password
5. Verifica HMAC constant-time (timing-safe comparison)
6. Validazione password secondo policy GDPR
7. Hash Argon2id → salva atomicamente
8. Token invalidato immediatamente → login automatico
```

---

## 2. Gestione Sessioni e Cookie

### Sessione standard

| Elemento | Valore |
|----------|--------|
| Token | `secrets.token_urlsafe(32)` (256 bit di entropia) |
| Storage | DB colonna `users.session_token` + cookie browser |
| TTL | 30 giorni |
| Auto-logout inattività | 8 ore (`SESSION_INACTIVITY_HOURS = 8`) |
| Invalidazione | Immediata se token non trovato in DB |
| Logout esplicito | Cookie impostato con expiry 1970 + token rimosso da DB |

### Cookie — Differenze tra frontend

| Attributo | Next.js | Streamlit |
|-----------|---------|-----------|
| HttpOnly | ✅ Sì | ❌ No (limitazione `extra-streamlit-components`) |
| Secure | ✅ Sì | ✅ Sì |
| SameSite | Lax | Strict |
| Protezione XSS | ✅ Completa (cookie non leggibile da JS) | ⚠️ Parziale (Secure+SameSite proteggono, ma JS può leggere) |

### Cookie impersonazione admin

| Attributo | Valore |
|-----------|--------|
| Nome | `oneflux_impersonate` |
| Contenuto | Flag tecnico `"1"` (no PII in chiaro) |
| HttpOnly | ✅ Sì |
| TTL | 30 minuti |
| Email cliente | Derivata server-side da `GET /api/admin/impersona/status` |

**Perché no email nel cookie:** prima dell'implementazione rev.25, il cookie conteneva l'email in chiaro — era leggibile da JS e vulnerabile a XSS (Art. 32 GDPR). Fix: cookie = flag tecnico, email = fetch server-side con session_backup.

---

## 3. Rate Limiting

| Funzione | Limite | Meccanismo |
|----------|--------|-----------|
| Login | 5 tentativi → 15 min lockout | Persistente su tabella `login_attempts` (DB) |
| Reset password | 1 richiesta / 5 min | In-memory dict thread-safe |
| Upload file | 100 file / 200 MB | Per singolo upload |
| Classificazione AI | 1.000/giorno per ristorante | Counter in `constants.py` |
| Chat AI | 0–30/giorno (per piano) | Tabella `chat_usage_log` |

**Perché il rate limiting login è persistente su DB e non in-memory:** gli in-memory reset al riavvio del processo. In produzione il processo Streamlit può riavviarsi (deploy, crash) — senza persistenza il lockout verrebbe bypassato.

---

## 4. Admin Guard (FastAPI)

Il guard `_verify_admin` introdotto in Fase 7 è il **prerequisito di sicurezza fondamentale** del pannello admin. Prima il `_verify_worker_key` non verificava l'identità admin.

```python
async def _verify_admin(request: Request, token: str = Depends(oauth2_scheme)):
    # 1. Verifica WORKER_SECRET_KEY (ogni richiesta al worker)
    _verify_worker_key(request)
    # 2. Decodifica bearer token → user_id
    user = get_user_by_session_token(token)
    # 3. Verifica is_admin flag
    if not user or not user.get("is_admin"):
        raise HTTPException(403, "Admin required")
    return user
```

---

## 5. Misure di Sicurezza Complete

| Categoria | Misura | Dettaglio |
|-----------|--------|-----------|
| **Autenticazione** | Argon2id | m=65536, OWASP raccomandato |
| **Sessioni** | Token opaco alta entropia + cookie 30gg | Auto-logout 8h, invalidazione su token mancante |
| **Cookie Next.js** | HttpOnly + Secure + SameSite=Lax | Cookie non leggibile da JS |
| **Cookie Streamlit** | Secure + SameSite=Strict | Parziale (no HttpOnly per limitazione libreria) |
| **Rate limiting** | Login su DB + Reset in-memory | Login persistente attraverso i riavvii |
| **IDOR** | `.eq('user_id', user_id)` su ogni query | Ogni lettura/scrittura include filtro owner |
| **XSS** | `html.escape()` | Su tutti gli output user-generated in HTML |
| **CSRF** | `enableXsrfProtection = true` (Streamlit) | Nativo Streamlit |
| **SQL Injection** | Parametrized queries | Supabase client non permette raw SQL |
| **XXE** | `defusedxml` | Validazione XML prima del parsing FatturaPA |
| **SSRF** | Whitelist host | Solo `*.invoicetronic.com/.it` su HTTPS per fetch XML remoti |
| **File Upload** | Magic bytes validation | Verifica header file oltre all'estensione |
| **File Upload** | Size limits | 100 file, 200 MB totale, 50 MB per P7M |
| **Path Traversal** | Sanitizzazione percorsi | `nome_file` e `file_origine` sanificati |
| **Worker API** | Porta 8000 interna | Non esposta pubblicamente in produzione |
| **Input AI** | Control char removal + 300 char truncation | Prima di inviare a OpenAI |
| **Error handling** | `showErrorDetails = false` | Mai esporre stack trace in produzione |
| **Logging** | No PII nei log | Email mai in chiaro, password mai loggate |
| **CORS** | `enableCORS = false` (Streamlit) | Disabilitato |
| **Reset Token** | `secrets.token_urlsafe(32)` | 256 bit entropia, verifica constant-time |
| **Secrets** | `st.secrets` / env vars Railway/Vercel | Mai hardcoded nel codice |
| **Dependencies** | `requirements-lock.txt` | 100 pacchetti freezati (supply chain security) |
| **WORKER_SECRET_KEY** | 64 char, fail-closed | Worker non si avvia senza chiave (salvo `WORKER_DEV_MODE=1`) |
| **Admin guard** | Worker key + bearer token + `is_admin` | Doppia verifica su ogni endpoint admin |

---

## 6. Isolamento Multi-Tenant

Ogni query al database include obbligatoriamente `user_id` E `ristorante_id`:

```python
# Pattern corretto — ogni query
supabase.table("fatture")
    .select("*")
    .eq("user_id", user_id)
    .eq("ristorante_id", ristorante_id)
    .not_.is_("deleted_at", "null")
    .execute()
```

**RLS Supabase:** Attivo come secondo livello di sicurezza su tutte le tabelle. `auth.uid()` è sempre NULL perché usiamo auth custom (non Supabase Auth). L'accesso avviene tramite `service_role_key` che bypassa RLS — per questo i filtri `user_id` in Python sono critici e non delegabili.

---

## 7. Sicurezza Webhook Invoicetronic

| Misura | Dettaglio |
|--------|-----------|
| HMAC-SHA256 | Firma di ogni webhook — rifiuta richieste senza firma valida |
| Anti-replay | Timestamp webhook > 5 minuti → rifiutato |
| SSRF whitelist | Solo `*.invoicetronic.com` / `*.invoicetronic.it` su HTTPS |
| Redirect policy | `redirect: 'error'` — nessun redirect seguito |
| Timeout | 3 secondi per fetch XML remoto |
| Risposta 200 SEMPRE | Evita retry storm da Invoicetronic su errori interni |
| Idempotenza | `ON CONFLICT (event_id) DO NOTHING` — stesso evento processato una sola volta |

---

## 8. Compliance GDPR

### Titolare del trattamento

**Recoma System S.r.l.**
P.IVA: IT09599210961
Referente: Mattia D'Avolio
Contatto: md@oneflux.it

### Responsabili del trattamento (sub-processori)

| Provider | Servizio | Localizzazione dati |
|---------|---------|---------------------|
| Supabase | Database PostgreSQL | EU Frankfurt |
| OpenAI | AI classificazione e briefing | USA (DPA firmato) |
| Brevo | Email transazionali | EU |
| Invoicetronic | SDI intermediario | Italia |
| Vercel | Next.js hosting | USA + Edge EU |
| Railway | FastAPI Worker + queue-worker | USA |

### Basi giuridiche

- **Contratto (Art. 6.1.b)** — per il servizio di gestione fatture
- **Consenso (Art. 6.1.a)** — per marketing e comunicazioni promozionali
- Consenso esplicito raccolto all'onboarding con `privacy_accepted_at` (scritto solo con checkbox spuntato — fix G1 rev.25)

### Documenti legali

- **Privacy & Cookie Policy v4.0** — `/privacy` (Next.js), `privacy_policy.py` (Streamlit)
- **Terms of Service** — `/termini` (Next.js), sezione in `privacy_policy.py`
- Nota legale: "Non costituisce sistema di Conservazione Sostitutiva ai sensi del D.M. 17 giugno 2014"

### Cookie

| Cookie | Tipo | Scopo |
|--------|------|-------|
| `oneflux_session` | Tecnico | Sessione autenticata (HttpOnly, Next.js) |
| `oneflux_impersonate` | Tecnico | Flag impersonazione admin (HttpOnly) |
| `oneflux_session_backup` | Tecnico | Backup token admin durante impersonazione (HttpOnly) |
| `oneflux_cookie_notice_v1` | Tecnico | Dismiss banner cookie (localStorage) |

**No cookie di marketing, tracking o analisi.** Banner dismissibile senza Accept/Reject (solo cookie tecnici — Provvedimento Garante 10/06/2021).

### Diritto all'oblio (Art. 17)

"Elimina Account" self-service → eliminazione permanente a cascata su 16+ tabelle:
`fatture`, `prodotti_utente`, `classificazioni_manuali`, `upload_events`, `margini_mensili`, `review_confirmed`, `review_ignored`, `ricette`, `ingredienti_workspace`, `diario_eventi`, `turni_personale`, `inventario_voci`, `custom_tags`, `ai_usage_events`, `login_attempts`, `ristoranti`, `category_change_log`, `cache_version` + riga `users`

### Portabilità dati (Art. 20)

Export JSON da pagina Impostazioni — 10+ tabelle incluse:
account, ristoranti, fatture, classificazioni_manuali, upload_events, ai_usage_events, ricette, diario_eventi, margini_mensili, prodotti_utente, custom_tags

### Data Retention

| Dato | Retention |
|------|-----------|
| Fatture nel DB | Finché l'utente non le elimina |
| Fatture cestino | 30 giorni, poi eliminazione definitiva |
| Fatture > 2 anni | Auto-eliminazione (job `fatture_retention_2y`) |
| XML Invoicetronic | Purge GDPR dopo 24h (`purge_processed_xml_content`) |
| Log upload | Non eliminati automaticamente |
| Sessioni | Invalidate su logout o scadenza 30gg |
| Reset token | Invalido dopo 15 minuti o utilizzo |

### Anonimizzazione AI

Prima di inviare dati a OpenAI per briefing e chat:
- Nomi prodotti → segnaposto ("Prodotto_1", "Prodotto_2", ecc.)
- Nomi fornitori → segnaposto ("Fornitore_123")
- Mai dati personali inviati a OpenAI

### Onboarding GDPR-compliant

1. Admin inserisce: email + nome ristorante + P.IVA + ragione sociale
2. Sistema crea account `attivo=False`, `password_hash=NULL`
3. Email automatica con token 24h → link Next.js `/reset-password?token=...&onboarding=1`
4. Cliente imposta password sua (admin non vede mai la password)
5. Checkbox obbligatorio: "Ho letto e accetto Privacy Policy e Termini"
6. `privacy_accepted_at` scritto nel DB **solo** con consenso reale
7. Account diventa `attivo=True`

---

## 9. Sicurezza Next.js vs Streamlit

| Aspetto | Next.js | Streamlit |
|---------|---------|-----------|
| Cookie sessione | HttpOnly (JS non legge) | No HttpOnly (JS può leggere) |
| Cookie impersonazione | HttpOnly + no PII | Cookie con email in chiaro (legacy, deprecato) |
| Header sicurezza | CSP, HSTS, X-Frame-Options | Gestiti da Streamlit Cloud |
| Auth edge | Middleware protegge a edge (blacklist invertita) | Auth in-process Python |
| CORS | Gestito da Next.js | `enableCORS=false` |

La migrazione a Next.js migliora significativamente il profilo di sicurezza, in particolare eliminando il limite HttpOnly dei cookie di Streamlit.

---

*Sicurezza e GDPR v6.0 — 5 Giugno 2026*
