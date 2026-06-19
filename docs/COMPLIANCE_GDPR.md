# ONEFLUX — Dossier Compliance GDPR

Documento di sintesi della conformità al Regolamento UE 2016/679 (GDPR) e al
D.lgs. 196/2003 (Codice Privacy). Uso interno + materiale da fornire a clienti B2B
che lo richiedano o in caso di controllo.

**Ultimo aggiornamento:** 19 giugno 2026
**Titolare del trattamento:** Recoma System S.r.l. — P.IVA IT09599210961
**Referente:** Mattia D'Avolio — md@oneflux.it
**DPO:** non nominato (non ricorrono gli obblighi dell'art. 37 GDPR: no trattamento
su larga scala di categorie particolari, no monitoraggio sistematico su larga scala).

> Le pagine legali per l'utente finale sono in-app: `/privacy` (Privacy & Cookie
> Policy) e `/termini` (Termini di Servizio).

---

## 1. Registro dei Trattamenti (Art. 30)

| Trattamento | Finalità | Base giuridica | Categorie dati | Conservazione |
|---|---|---|---|---|
| Gestione account | Erogazione servizio, autenticazione | Art. 6.1.b (contratto) + consenso | Email, nome ristorante, P.IVA, ragione sociale, password (hash) | Durata del rapporto; cancellazione self-service |
| Analisi fatture | Categorizzazione costi, report margini | Art. 6.1.b (contratto) | Fatture elettroniche, importi, fornitori | Fino a eliminazione volontaria; XML grezzo purgato dopo processing |
| Ricezione SDI | Ingest automatico fatture da Invoicetronic | Art. 6.1.b (contratto) | Metadati ed eventi webhook fattura | XML purgato dalla coda entro 24h dall'elaborazione |
| Dati operativi | Foodcost, ricette, margini, diario | Art. 6.1.b (contratto) | Ricette, ingredienti, note, margini, ricavi | Durata del rapporto |
| Log operativi | Trasparenza, supporto tecnico | Art. 6.1.f (legittimo interesse) | Log upload, log utilizzo AI (modello, token, costo) | Durata dell'account |
| Sicurezza accessi | Anti-brute-force | Art. 6.1.f (legittimo interesse) | Tentativi di login | 15 minuti (rate limiting), poi eliminati |

---

## 2. Sub-responsabili del Trattamento (Art. 28)

| Fornitore | Ruolo | Sede dati | Garanzie trasferimento |
|---|---|---|---|
| Supabase Inc. | Hosting database PostgreSQL | UE — Frankfurt 🇩🇪 | Dati persistiti solo in UE |
| OpenAI LP | Categorizzazione AI | USA | SCC UE; dati elaborati on-the-fly, non usati per training |
| Brevo SAS | Email transazionale (SMTP) | UE — Francia 🇫🇷 | Nessun contenuto fattura trasmesso |
| Invoicetronic S.r.l. | Ricezione fatture SDI + webhook | Italia 🇮🇹 | XML grezzo non archiviato dopo la consegna |
| Vercel Inc. | Hosting frontend (Next.js) | UE / USA | SCC UE; nessun dato applicativo persistito |
| Railway Corp. | Worker elaborazione + API | USA | SCC UE; elaborazione in memoria, nessun dato persistito |

I trasferimenti extra-UE (OpenAI, Railway, Vercel) sono coperti da **Clausole
Contrattuali Standard UE (SCC)**. Il database con i dati persistiti resta in UE.

---

## 3. Misure di Sicurezza Tecniche e Organizzative (Art. 32)

**Tecniche:**
- Password: hashing Argon2id (m=65536, t=3, p=1) — standard OWASP; password in chiaro mai archiviata.
- Cifratura in transito: TLS 1.3 su tutti i canali.
- Cifratura a riposo: AES-256 (gestita da Supabase).
- Controllo accessi multi-tenant: Row-Level Security PostgreSQL **attiva e forzata**
  sulle tabelle con dati cliente + filtri applicativi per utente/ristorante.
  L'accesso applicativo passa esclusivamente dal ruolo `service_role`.
- Sessioni: token opachi ad alta entropia, cookie **HttpOnly + Secure + SameSite=Lax**
  (token mai esposto a JavaScript), scadenza e invalidazione esplicita al logout.
- Rate limiting persistente su DB (login + reset password) anti-brute-force.
- Protezioni applicative: IDOR (filtro per identità su ogni operazione), XXE
  (defusedxml), SSRF (whitelist host), validazione magic-bytes sugli upload.
- Webhook fatture autenticato via firma **HMAC-SHA256 + anti-replay** (non dipende
  da chiavi JWT condivise).

**Organizzative:**
- Suite di test automatizzati (~9530 Python + 18 Deno) eseguiti in CI su ogni rilascio.
- Audit di sicurezza periodico: ultimo 19/06/2026 — advisor Supabase **0 ERROR
  sicurezza, 0 WARN performance**; chiusi 2 vettori di lettura non autorizzata
  (tabella sessioni e RPC interne) prima del go-live.
- Backup database: Point-in-Time Recovery (piano Supabase Pro).
- Segregazione segreti: chiavi solo lato server (Railway/Vercel/Supabase), mai nel
  bundle client né nel repository.

---

## 4. Diritti dell'Interessato (Art. 15–22) — procedura

| Diritto | Modalità di esercizio | Implementazione |
|---|---|---|
| Accesso (15) | Interfaccia app | Visualizzazione dati nelle sezioni dedicate |
| Rettifica (16) | Profilo / Impostazioni | Modifica dati anagrafici |
| **Cancellazione (17)** | **Self-service** | Impostazioni → Privacy e dati → "Elimina il mio account" → cancellazione permanente a cascata su tutte le tabelle |
| Limitazione (18) | Email al Titolare | Evasione entro 30 giorni |
| **Portabilità (20)** | **Self-service** | Impostazioni → Privacy e dati → "Scarica i miei dati" → export JSON strutturato |
| Opposizione (21) | Email al Titolare | Evasione entro 30 giorni |

Reclamo all'autorità di controllo: **Garante per la Protezione dei Dati Personali**
(www.garanteprivacy.it).

---

## 5. Data Retention e Cancellazione

- Dati account e operativi: per la durata del rapporto contrattuale.
- File XML/P7M grezzi: purgati dopo il processing; quelli via SDI entro 24h dalla coda.
- Tentativi di accesso: 15 minuti.
- Alla cancellazione dell'account: eliminazione **permanente e a cascata** (FK
  ON DELETE CASCADE) su fatture, ristoranti, ricette, ricavi, margini, sessioni,
  tag, notifiche, ecc. La memoria AI globale (dati aggregati non riferibili al
  singolo) non costituisce dato personale dell'interessato e non viene esportata.

---

## 6. Cookie

Utilizzati **esclusivamente cookie tecnici** strettamente necessari (sessione di
login, funzionamento). Nessun cookie di profilazione, analytics o di terze parti;
nessun pixel di tracciamento; font self-hosted. Ai sensi del Provvedimento Garante
del 10/06/2021 i cookie tecnici **non richiedono consenso preventivo** ma solo
informativa, fornita in-app (`/privacy`) e tramite banner informativo non bloccante.

| Cookie | Tipo | Scadenza | Contenuto |
|---|---|---|---|
| `oneflux_session` | Tecnico/sessione | 30 giorni | Token opaco ad alta entropia |
| `oneflux_session_backup` | Tecnico/admin | 8 ore | Token admin durante impersonazione di supporto |
| `oneflux_impersonate` | Tecnico/admin | 8 ore | Flag (nessun dato personale) |

Tutti `HttpOnly + Secure + SameSite=Lax`.

---

## 7. Note ed esclusioni

- Il servizio **non effettua Conservazione Sostitutiva** ai sensi del D.M. 17/06/2014:
  l'utente resta responsabile della conservazione fiscale decennale presso canali AgID.
- Il servizio **non sostituisce consulenza fiscale/contabile/legale**.
- La classificazione AI ha natura indicativa; l'utente dispone di strumenti di
  revisione e conferma manuale.

---

## 8. Materiale da completare / verificare prima del go-live (1/7/2026)

- [ ] **Sede legale del Titolare** da inserire nell'informativa (`/privacy`, `/termini`,
      sezione Titolare) e in questo dossier — al momento è indicata solo P.IVA + email.
- [ ] Eventuale **nomina formale dei sub-responsabili** (DPA firmati con i fornitori),
      se richiesto da clienti B2B strutturati.
