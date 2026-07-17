# ONEFLUX — Sicurezza tecnica

**Aggiornamento:** 17 luglio 2026 — verificato contro il codice.

Le **misure tecniche** di sicurezza e il **perché** di ognuna. Per la conformità
legale (registro trattamenti, DPA, DPIA, diritti dell'interessato) la fonte è
`docs/COMPLIANCE_GDPR.md`: è l'unico documento da fornire a un cliente B2B o in
caso di controllo, ed è più aggiornato di questo su tutto ciò che è legale.

Streamlit è dismesso dall'8/6/2026: qui si descrive solo Next.js + worker.

---

## 1. Il pilastro da capire prima di tutto

**L'auth è custom, non Supabase Auth.** `auth.uid()` è **sempre NULL** e l'app
accede con `service_role_key`, che **bypassa RLS**.

Conseguenza non negoziabile: i filtri applicativi `user_id` / `ristorante_id` in
Python **sono** la sicurezza multi-tenant. RLS è la seconda rete, non la prima.
Ogni query che dimentica il filtro è una fuga di dati fra clienti.

```python
supabase.table("fatture").select("*") \
    .eq("user_id", user_id) \
    .eq("ristorante_id", ristorante_id) \
    .not_.is_("deleted_at", "null") \
    .execute()
```

Corollario (audit 20/06): la **anon key è pubblica** per definizione. Qualsiasi
tabella o RPC raggiungibile con quella chiave via PostgREST scavalca il worker e
l'auth. Per questo RLS è attiva **e forzata**, e i GRANT sono solo a
`service_role`.

---

## 2. Autenticazione

| Elemento | Valore | Perché |
|---|---|---|
| Hashing | Argon2id, m=65536, t=3, p=1 | OWASP; **non cambiare i parametri** |
| Migrazione legacy | Auto da SHA256 al primo login | Nessun utente resta su hash debole |
| Password minima | 10 caratteri, 3/4 classi | GDPR Art.32 + Garante |
| Blacklist | 24+ password comuni, incluse varianti italiane ("ristorante", "pizzeria") | I clienti sono ristoratori |
| No dati personali | Email e nome ristorante vietati in password | Indovinabili |

**Reset password:** token `secrets.token_urlsafe(32)` + codice 6 cifre, scadenza
15 minuti, confronto **constant-time**, token invalidato all'uso.

---

## 3. Sessioni

Dal 6/6/2026 le sessioni stanno nella **tabella `sessioni`** (N token per utente,
cap 5), non più in `users.session_token`. Gestione in `services/session_service.py`.

| Elemento | Valore |
|---|---|
| Token | `secrets.token_urlsafe(32)` — opaco, 256 bit |
| TTL | 30 giorni |
| Auto-logout inattività | 8 ore (`SESSION_INACTIVITY_HOURS`, `config/constants.py`) |
| Revoca | `revoked_at` sulla riga; invalidazione immediata |
| Cookie | **HttpOnly + Secure + SameSite=Lax** |

Il cookie è HttpOnly: il token **non è leggibile da JavaScript**. Era il limite
principale del vecchio frontend Streamlit, ed è il motivo per cui il profilo di
sicurezza è migliorato con la migrazione.

**Cookie impersonazione admin** (`oneflux_impersonate`): contiene solo un flag
tecnico `"1"`, mai l'email. L'email si deriva server-side da
`GET /api/admin/impersona/status`. Prima conteneva l'email in chiaro leggibile da
JS — vulnerabile a XSS (Art. 32).

---

## 4. Rate limiting

| Funzione | Limite | Dove |
|---|---|---|
| Login | 5 tentativi → 15 min | Tabella `login_attempts` (**DB**) |
| Reset password | 1 / 5 min | In-memory |
| Upload | 100 file / 200 MB | Per upload |
| Classificazione AI | 1.000/giorno per ristorante | `constants.py` |
| Chat AI | 0–30/giorno per piano | `chat_usage_log` |

**Perché il login è persistente su DB:** un contatore in memoria si azzera al
riavvio del processo. Con deploy e restart frequenti, il lockout sarebbe
aggirabile aspettando un redeploy.

---

## 5. Le due difese del pannello admin

1. **`_verify_admin`** (worker): verifica `WORKER_SECRET_KEY` → decodifica bearer
   token → controlla `is_admin`. Prima esisteva solo `_verify_worker_key`, che
   **non verificava l'identità**: chiunque avesse la worker key era admin.
2. **`admin/layout.tsx`** (Next.js): blocca la route lato server.

**Guard di pagina** (`requirePagina`, `apps/web/src/lib/page-guard.ts`): le pagine
con feature flag chiamano `requirePagina(flag)` in cima. Flag spento →
`notFound()`. Prima `pagine_abilitate` filtrava **solo la sidebar**, quindi l'URL
diretto era raggiungibile. Doppia difesa con il gate tool della chat (`_TOOL_FLAG`).

> Non sostituisce l'isolamento dati del §1: è controllo di accesso alla
> **funzionalità**, non al **dato**.

---

## 6. Misure applicative

| Vettore | Misura |
|---|---|
| IDOR | Filtro identità su ogni query (§1) |
| XSS | `html.escape()` su output user-generated; cookie HttpOnly |
| SQL Injection | Query parametrizzate (il client Supabase non permette raw SQL) |
| XXE | `defusedxml` prima del parsing FatturaPA |
| SSRF | Whitelist host: solo `*.invoicetronic.com/.it` su HTTPS, `redirect: 'error'`, timeout 3s |
| Upload | Validazione **magic bytes** (non l'estensione) + limiti 100 file/200 MB/50 MB per P7M |
| Path traversal | `nome_file` e `file_origine` sanificati |
| Prompt injection | Control char removal + troncamento 300 char prima di OpenAI |
| Secrets | Solo env server-side (Railway/Vercel/Supabase). Mai `NEXT_PUBLIC_*`, mai nel repo |
| Worker | `WORKER_SECRET_KEY` 64 char, **fail-closed**: non si avvia senza (salvo `WORKER_DEV_MODE=1`) |
| Log | Nessuna PII: email mai in chiaro, password mai loggate |
| Supply chain | `requirements-lock.txt` (100 pacchetti freezati) |

---

## 7. Webhook Invoicetronic

| Misura | Perché |
|---|---|
| HMAC-SHA256 su ogni richiesta | È **l'unica** autenticazione: `verify_jwt=false` è dichiarato in `config.toml`, quindi non dipende dalla anon key pubblica |
| Anti-replay ±300s | Una richiesta catturata non è riutilizzabile |
| Risposta **200 sempre** | Un 500 scatena retry storm da Invoicetronic |
| `ON CONFLICT (event_id) DO NOTHING` | Idempotenza: stesso evento = una sola fattura |
| Purge XML dopo 24h | Minimizzazione GDPR |

Test: 18 test Deno (HMAC + routing), in CI.

---

## 8. Anonimizzazione prima dell'AI

Prima di ogni chiamata a OpenAI per briefing e chat:
- nomi prodotti → `Prodotto_1`, `Prodotto_2`…
- nomi fornitori → `Fornitore_123`
- ripristinati **dopo** la risposta

I nomi veri non escono mai dall'infrastruttura.

---

## 9. Storico audit

| Data | Esito |
|---|---|
| 19/06/2026 | Chiusi 2 leak: tabella `sessioni` e 6 RPC worker leggibili con anon key (account takeover / fatture cross-tenant) |
| 20/06/2026 | Chiuse 14 RPC SECURITY DEFINER residue; `search_path` su 13 trigger; advisor 43 WARN → 1 |
| 06/07/2026 | Riverifica post go-live: advisor **0 ERROR sicurezza, 0 WARN performance** |

Limite noto: `auth_leaked_password_protection` è disattivabile solo dal piano
Supabase Pro — non è una configurazione mancante ma un limite del piano Free.

---

*Conformità legale, DPA e DPIA: `docs/COMPLIANCE_GDPR.md` — è quello autorevole.*
