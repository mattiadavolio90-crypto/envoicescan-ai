# 🔒 Conformità GDPR e Sicurezza - Analisi Completa

**Applicazione:** FCI - Fatture e Categorizzazione Intelligente  
**Data Analisi:** 3 Febbraio 2026  
**Versione:** 2.5+  
**Target:** Aziende B2B (settore ristorazione e multi-settore)

---

## 📊 STATO ATTUALE: RIEPILOGO ESECUTIVO

### Livello Sicurezza Complessivo: **7.5/10** ⭐⭐⭐⚪

**Giudizio:** MEDIO-ALTO - Idoneo per deploy con completamenti documentali

| Ambito | Stato | Valutazione |
|--------|-------|-------------|
| **Sicurezza Tecnica** | ✅ SOLIDA | 9/10 |
| **GDPR Art.32 (Sicurezza)** | ✅ CONFORME | 9/10 |
| **GDPR Art.13-17 (Trasparenza)** | ⚠️ PARZIALE | 5/10 |
| **GDPR Art.30 (Registro trattamenti)** | ❌ MANCANTE | 2/10 |
| **Resilienza Attacchi** | ⚠️ MEDIA | 6/10 |
| **Documentazione Legale** | ❌ INSUFFICIENTE | 3/10 |

**Criticità:** Applicazione tecnicamente solida ma RICHIEDE completamento documentazione legale e implementazione diritti utente prima di rilascio commerciale.

---

## ✅ PARTE 1: COSA È GIÀ IMPLEMENTATO

### 1.1 Sicurezza Autenticazione (ECCELLENTE)

#### ✅ Password Hashing - Argon2
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
- Algoritmo: Argon2 (vincitore Password Hashing Competition 2015)
- Standard: Superiore a bcrypt, SHA-256, MD5
- Caratteristiche: Resistente a GPU cracking, time-memory trade-off
- Migrazione automatica: Vecchie password SHA-256 vengono convertite al primo login

**Conformità:**
- ✅ GDPR Art.32.1.a (cifratura dati personali)
- ✅ ISO/IEC 27001:2013 - A.9.4.3 (sistema gestione password)
- ✅ OWASP Password Storage Cheat Sheet 2025

**File implementazione:** `services/auth_service.py` (linee 28-30, 300-350)

---

#### ✅ Validazione Password GDPR Compliant
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
Validazione automatica con requisiti normativi:

1. **Lunghezza minima:** 10 caratteri (best practice 2026, GDPR minimo 8)
2. **Complessità:** Almeno 3 categorie su 4:
   - Lettere maiuscole (A-Z)
   - Lettere minuscole (a-z)
   - Numeri (0-9)
   - Simboli speciali (!@#$%^&*...)
3. **Blacklist password comuni:** OWASP Top 20 + varianti italiane
4. **NO dati personali:** Blocca email, P.IVA, nome ristorante nella password
5. **NO pattern sequenziali:** Blocca "123456", "abcdef", caratteri ripetuti

**Conformità:**
- ✅ Garante Privacy Italia - Provvedimento 8 aprile 2010
- ✅ GDPR Art.32.1 (misure tecniche appropriate)
- ✅ Linee Guida ENISA 2020 (autenticazione forte)

**File implementazione:** `services/auth_service.py` (funzione `valida_password_compliance`)

---

#### ✅ Sistema Token Reset Password
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
- Token UUID v4 crittograficamente sicuro (128 bit casuali)
- Validità temporale: 24 ore (configurabile)
- Monouso: Token invalidato dopo utilizzo
- Storage sicuro: Campo `reset_token` database con timestamp scadenza
- Invio via email: Link univoco `?reset_token=UUID`

**Conformità:**
- ✅ GDPR Art.32.2 (capacità assicurare disponibilità)
- ✅ OWASP Authentication Cheat Sheet

**File implementazione:** `services/auth_service.py` (funzioni token), `app.py` (gestione query param)

---

#### ✅ Separazione Admin/Cliente (No Password Setting)
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
Flow GDPR compliant per creazione account:
1. Admin crea cliente inserendo: email, nome ristorante, P.IVA, ragione sociale
2. Sistema genera token attivazione (24h)
3. Email automatica inviata al cliente con link sicuro
4. Cliente clicca link e SOLO LUI imposta la propria password
5. Admin NON conosce né può vedere le password clienti

**Conformità:**
- ✅ GDPR Art.32.4 (minimizzazione personale accesso)
- ✅ Principio "least privilege" (ISO 27001)
- ✅ Segregation of duties (best practice security)

**File implementazione:** `pages/admin.py` (form creazione), `services/auth_service.py` (funzione `crea_cliente_con_token`)

---

### 1.2 Isolamento Dati (ECCELLENTE)

#### ✅ Row Level Security (RLS) PostgreSQL
**Stato:** IMPLEMENTATO SU TUTTE LE TABELLE

**Descrizione:**
PostgreSQL RLS attivo su ogni tabella contenente dati utente:

**Tabella `fatture`:**
- Policy: Utente vede SOLO le proprie fatture
- Filtro: `user_id = auth.uid()`
- Admin bypass: Policy separata per `is_admin = true`

**Tabella `classificazioni_manuali`:**
- Policy: Utente modifica SOLO le proprie categorizzazioni
- Filtro: `user_id = auth.uid()`

**Tabella `prodotti_utente`:**
- Policy: Isolamento prodotti personalizzati per utente
- Filtro: `user_id = auth.uid()`

**Tabella `ristoranti`:**
- Policy: Utente gestisce SOLO i propri ristoranti/sedi
- Filtro: `user_id = auth.uid()`
- Bypass RLS: Funzione RPC `create_ristorante_for_user()` con SECURITY DEFINER

**Tabella `prodotti_master` (memoria globale):**
- Policy: Tutti leggono (condivisa), tutti scrivono (collaborativa)
- Nessun dato personale contenuto

**Conformità:**
- ✅ GDPR Art.32.1.b (riservatezza dati personali)
- ✅ ISO/IEC 27001 - A.9.4.1 (restrizione accesso informazioni)
- ✅ Defense in depth (livello database, non solo app)

**File implementazione:** Migrations `003_fix_rls_permissions.sql`, `010_multi_ristorante.sql`, `016_fix_ristoranti_rls_insert.sql`

---

#### ✅ Session Management Sicura
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
- Bearer token Supabase con scadenza automatica
- Session state Streamlit isolata per utente
- Nessun dato sensibile in localStorage browser
- Logout cancella completamente sessione server + client

**Conformità:**
- ✅ OWASP Session Management Cheat Sheet
- ✅ GDPR Art.32 (controllo accessi)

**File implementazione:** `app.py` (gestione session_state), Supabase Auth integrato

---

### 1.3 Validazione Dati Fiscali (OTTIMO)

#### ✅ Validatore Partita IVA Italiana
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
Validazione multi-livello:

1. **Formato:** Esattamente 11 cifre numeriche
2. **Normalizzazione:** Rimozione automatica spazi, trattini, prefissi "IT"
3. **Checksum Luhn:** Algoritmo ufficiale Ministero Finanze (D.P.R. 633/1972)
4. **Constraint database:** UNIQUE su campo `partita_iva` (no duplicati)
5. **Validazione upload XML:** Confronto P.IVA cessionario vs utente loggato

**Conformità:**
- ✅ D.P.R. 633/1972 (IVA - formato partita IVA)
- ✅ Direttiva UE 2006/112/CE (sistema IVA comune)
- ✅ Prevenzione frodi fiscali (matching fattura-destinatario)

**File implementazione:** `utils/piva_validator.py`, `services/invoice_service.py` (estrazione XML)

---

#### ✅ Validazione Fatture XML
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
Controllo sicurezza upload fatture elettroniche:

1. **Estrazione P.IVA cessionario:** Parsing nodo `CessionarioCommittente/DatiAnagrafici/IdFiscaleIVA/IdCodice`
2. **Confronto automatico:** P.IVA fattura vs P.IVA utente loggato
3. **Blocco upload:** Se P.IVA non corrisponde → errore chiaro
4. **Bypass controllo:** Se utente NON ha P.IVA configurata (retrocompatibilità)

**Conformità:**
- ✅ Prevenzione caricamento fatture altrui (data breach)
- ✅ GDPR Art.5.1.f (integrità e riservatezza)
- ✅ Anti-GDPR violation (no mixing dati fiscali diversi titolari)

**File implementazione:** `services/invoice_service.py` (funzione `estrai_piva_cessionario_xml`), `app.py` (logica controllo upload)

---

### 1.4 Audit e Logging (BUONO)

#### ✅ Logger Centralizzato
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
- Logging strutturato con timestamp automatici
- Livelli: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Tracciamento operazioni sensibili:
  - Login/logout utenti
  - Creazione/eliminazione clienti
  - Svuotamento memoria globale AI
  - Errori autenticazione
- Storage: Console + file log (se configurato)

**Conformità:**
- ✅ GDPR Art.32.1.d (capacità di verificare efficacia misure)
- ✅ ISO/IEC 27001 - A.12.4.1 (registrazione eventi)
- ⚠️ PARZIALE: Manca retention policy documentata

**File implementazione:** `config/logger_setup.py`, import in tutti i service

---

#### ✅ Tracking Password Changes
**Stato:** IMPLEMENTATO MA SOTTOUTILIZZATO

**Descrizione:**
- Campo database: `password_changed_at` (timestamp ultima modifica)
- Campo database: `login_attempts` (contatore tentativi falliti)
- Aggiornamento automatico al cambio password

**Conformità:**
- ✅ GDPR Art.32.1.d (accountability)
- ⚠️ INCOMPLETO: `login_attempts` non utilizzato attivamente per blocchi

**File implementazione:** Migrazione `009_add_piva_password.sql`, `services/auth_service.py`

---

### 1.5 Gestione Configurazioni (BUONO)

#### ✅ Secrets Management
**Stato:** IMPLEMENTATO E OPERATIVO

**Descrizione:**
- File `secrets.toml` escluso da Git (.gitignore)
- Template `secrets.toml.example` per sviluppatori
- API Keys mai hardcoded nel codice
- Streamlit secrets loader integrato

**Conformità:**
- ✅ OWASP Top 10:2021 - A02 (Cryptographic Failures)
- ✅ Best practice DevSecOps

**File implementazione:** `.streamlit/secrets.toml` (gitignored), `secrets.toml.example`

---

## ⚠️ PARTE 2: COSA MANCA PER CONFORMITÀ COMPLETA

### 2.1 DOCUMENTAZIONE LEGALE (PRIORITÀ MASSIMA) 🔴

#### ❌ Privacy Policy (Art.13 GDPR)
**Stato:** MANCANTE - OBBLIGATORIO

**Descrizione Mancanza:**
L'applicazione NON ha una Privacy Policy visibile agli utenti che informi su:
- Titolare del trattamento (dati azienda)
- Base giuridica trattamento (contratto, consenso, legittimo interesse)
- Tipologie dati raccolti (email, P.IVA, fatture XML, prodotti categorizzati)
- Finalità trattamento (gestione fatture, AI categorizzazione, supporto clienti)
- Durata conservazione dati
- Diritti utente (accesso, rettifica, cancellazione, portabilità, opposizione)
- Trasferimenti dati extra-UE (se presenti, es. OpenAI API)
- Modalità esercizio diritti

**Impatto Legale:**
- ❌ Violazione GDPR Art.13 → Sanzione fino a €10.000.000 o 2% fatturato annuo
- ❌ Violazione Codice Privacy italiano (D.Lgs. 196/2003 aggiornato)
- ❌ Possibili reclami utenti al Garante Privacy

**Come Implementare:**
1. **Documento Privacy Policy:**
   - Creare pagina dedicata accessibile da menu principale
   - Link "Privacy Policy" nel footer (sempre visibile)
   - Versioning: Data ultima modifica + archivio versioni precedenti

2. **Contenuti minimi obbligatori:**
   - Identità titolare: Ragione sociale, indirizzo, P.IVA, email DPO
   - Categorie dati: Email, password (hash), P.IVA, ragione sociale, fatture XML, prodotti categorizzati, token sessione
   - Finalità: Gestione account, categorizzazione AI, statistiche, supporto
   - Base giuridica: Esecuzione contratto (Art.6.1.b GDPR)
   - Destinatari: Supabase (hosting DB), OpenAI (API AI), Brevo (email), Streamlit Cloud (hosting app)
   - Trasferimenti extra-UE: OpenAI (USA) - clausole contrattuali tipo UE
   - Conservazione: Durata contratto + 10 anni (normativa fiscale fatture)
   - Diritti: Accesso, rettifica, cancellazione, portabilità, opposizione, reclamo Garante

3. **Modalità visualizzazione:**
   - Sidebar Streamlit: Link "📋 Privacy Policy" sempre visibile
   - Popup/expander con testo completo
   - Checkbox consenso alla registrazione: "Ho letto e accetto la Privacy Policy"
   - Link versione PDF scaricabile

4. **Template consigliato:**
   - Utilizzare generatore Privacy Policy GDPR (es. iubenda, Privacypolicies.com)
   - Far revisionare da avvocato specializzato privacy
   - Aggiornare ogni 12 mesi o a modifiche sostanziali

**Timeline implementazione:** 1-2 giorni (redazione) + 1 giorno (integrazione UI)

---

#### ❌ Cookie Policy e Banner Consenso
**Stato:** MANCANTE - PROBABILMENTE NECESSARIO

**Descrizione Mancanza:**
Non è visibile un cookie banner né policy sui cookie.

**Analisi necessità:**
1. **Streamlit session state:** Usa cookie sessione → Tecnicamente necessari (esenzione consenso Art.122 Codice Privacy)
2. **Supabase Auth:** Usa cookie autenticazione → Tecnicamente necessari (esenzione)
3. **Analytics/Tracking:** NON visibili nel codice → Se assenti, cookie policy semplificata sufficiente

**Come Implementare:**

**Scenario A - Solo cookie tecnici (più probabile):**
1. Breve informativa in Privacy Policy: "Utilizziamo solo cookie tecnici necessari al funzionamento"
2. Nessun banner consenso richiesto (Art.122 comma 1 Codice Privacy)
3. Elenco cookie usati: nome, finalità, durata

**Scenario B - Cookie analytics (Google Analytics, Hotjar, etc.):**
1. Cookie banner obbligatorio con:
   - Informativa chiara e completa
   - Consenso preventivo per cookie non tecnici
   - Possibilità rifiuto senza conseguenze
   - Gestione preferenze granulare
2. Integrazione con Cookiebot, OneTrust o soluzione GDPR compliant

**Raccomandazione:** Verificare con developer tool browser quali cookie sono effettivamente impostati, poi agire di conseguenza.

**Timeline implementazione:** 2 ore (se solo tecnici) / 1-2 giorni (se banner necessario)

---

#### ❌ Termini e Condizioni di Servizio
**Stato:** MANCANTE - FORTEMENTE CONSIGLIATO

**Descrizione Mancanza:**
Nessun contratto visibile tra fornitore servizio e cliente che regoli:
- Obblighi fornitore (uptime, supporto, SLA)
- Obblighi cliente (uso corretto, divieto abusi)
- Limitazioni responsabilità (AI errors, data loss)
- Proprietà intellettuale (codice vs dati cliente)
- Risoluzione controversie (foro competente)
- Modifiche unilaterali servizio

**Impatto Legale:**
- ⚠️ Non obbligatorio per GDPR, ma essenziale per tutela legale azienda
- ⚠️ Senza T&C: Difficile difendersi in caso controversie
- ⚠️ Responsabilità illimitata in caso errori AI o data loss

**Come Implementare:**
1. **Documento T&C:**
   - Pagina dedicata "Termini e Condizioni"
   - Link nel footer accanto Privacy Policy
   - Checkbox accettazione alla registrazione

2. **Contenuti minimi consigliati:**
   - Definizioni (servizio, utente, contenuti)
   - Oggetto contratto (fornitura SaaS categorizzazione fatture)
   - Obblighi fornitore: Best effort, no garanzia risultati AI, SLA uptime (es. 99%)
   - Obblighi cliente: Uso lecito, no reverse engineering, pagamento canoni
   - Proprietà dati: Fatture e dati cliente restano di proprietà cliente
   - Limitazione responsabilità: Esclusione danni indiretti, massimale danni diretti (es. 12 mesi canone)
   - Durata e recesso: Rinnovo automatico, preavviso recesso (es. 30gg)
   - Foro competente: Tribunale di [città sede]
   - Modifiche: Notifica 30gg prima, diritto recesso se non accettate

3. **Modalità visualizzazione:**
   - Stessa implementazione Privacy Policy
   - Versioning e archivio storico

**Timeline implementazione:** 2-3 giorni (redazione legale) + 1 giorno (integrazione UI)

---

#### ❌ Registro Trattamenti (Art.30 GDPR)
**Stato:** NON PRESENTE NEL CODICE - OBBLIGATORIO SE >250 DIPENDENTI O DATI SENSIBILI

**Descrizione Mancanza:**
Il registro dei trattamenti è un documento interno (non pubblico) che elenca TUTTI i trattamenti dati personali effettuati dall'azienda.

**Obbligatorietà:**
- ✅ Obbligatorio se: Azienda >250 dipendenti
- ✅ Obbligatorio se: Trattamento NON occasionale
- ✅ Obbligatorio se: Dati sensibili (salute, orientamento) → NON APPLICABILE qui
- ✅ CONSIGLIATO SEMPRE per compliance proattiva

**Come Implementare:**
1. **Creare file Excel/Word con:**
   - Nome trattamento (es. "Gestione account clienti B2B")
   - Finalità (es. "Erogazione servizio SaaS categorizzazione fatture")
   - Categorie interessati (es. "Titolari P.IVA settore ristorazione")
   - Categorie dati (es. "Email, password hash, P.IVA, ragione sociale, fatture XML")
   - Destinatari (es. "Supabase Inc., OpenAI LP, Brevo SAS")
   - Trasferimenti extra-UE (es. "OpenAI - USA - clausole contrattuali tipo")
   - Termini cancellazione (es. "Chiusura account + 10 anni obbligo fiscale")
   - Misure sicurezza (es. "Argon2, RLS, HTTPS, backup giornalieri")

2. **Aggiornamento:**
   - Revisione ogni 12 mesi
   - Aggiornamento immediato a modifiche sostanziali

3. **Storage:**
   - File privato, NON nel repository pubblico
   - Accessibile solo a: Titolare, DPO, audit Garante Privacy

**Timeline implementazione:** 1 giornata (compilazione template)

---

### 2.2 DIRITTI UTENTE (PRIORITÀ ALTA) 🟠

#### ❌ Diritto di Accesso (Art.15 GDPR)
**Stato:** PARZIALMENTE IMPLEMENTATO

**Descrizione Mancanza:**
Utente può vedere le proprie fatture nella UI, MA non ha funzione esplicita "Esporta tutti i miei dati" in formato strutturato.

**Come Implementare:**
1. **Funzione "Scarica i miei dati":**
   - Posizione: Menu utente o sezione "Il mio account"
   - Pulsante: "📥 Esporta tutti i miei dati (GDPR Art.15)"
   
2. **Contenuto export:**
   - File ZIP contenente:
     - `dati_account.json`: email, nome_ristorante, P.IVA, ragione_sociale, data_registrazione
     - `fatture/`: Cartella con XML originali + CSV estratti
     - `classificazioni.csv`: Tutte categorizzazioni manuali utente
     - `prodotti_personalizzati.csv`: Prodotti_utente
     - `log_accessi.csv`: Date login (ultimi 90gg)

3. **Formato:**
   - JSON per dati strutturati (machine-readable)
   - CSV per tabelle (Excel-compatible)
   - Tutti file in chiaro, NO password ZIP (è dati personali utente stesso)

4. **Tempistiche:**
   - Generazione immediata (< 30 secondi per utente normale)
   - Se grandi volumi: Email link download dopo elaborazione asincrona

**Timeline implementazione:** 1-2 giorni (funzione export + UI)

---

#### ❌ Diritto alla Cancellazione / Oblio (Art.17 GDPR)
**Stato:** MANCANTE - OBBLIGATORIO

**Descrizione Mancanza:**
NON esiste funzione "Elimina il mio account" per l'utente finale.
Admin può eliminare clienti, ma cliente NON può auto-eliminarsi.

**Come Implementare:**

**Opzione A - Cancellazione immediata (rischioso per fatture):**
1. **Funzione "Elimina account":**
   - Posizione: Sezione "Il mio account" → Pulsante rosso "🗑️ Elimina account"
   - Conferma tripla: "Digita 'ELIMINA' per confermare"
   - Warning: "ATTENZIONE: Eliminerà TUTTE le fatture e dati. IRREVERSIBILE."

2. **Logica cancellazione:**
   - DELETE CASCADE automatico su tutte le FK (fatture, classificazioni, ristoranti)
   - Conservazione: NULLA (oblio totale)
   - Log operazione: Solo timestamp + user_id (anonimizzato) per audit

3. **Problemi:**
   - ❌ Viola obbligo conservazione fatture 10 anni (D.P.R. 633/1972)
   - ❌ Cliente perde storico fiscale

**Opzione B - Anonimizzazione (CONSIGLIATA):**
1. **Funzione "Richiedi cancellazione dati":**
   - Utente fa richiesta via form
   - Sistema invia email notifica ad admin
   - Admin valuta richiesta (verifica obblighi fiscali)

2. **Se approvata:**
   - Anonimizzazione dati personali:
     - Email → `anonimo_<UUID>@deleted.local`
     - Nome_ristorante → `[Account eliminato]`
     - Ragione_sociale → NULL
     - Password → hash random
   - Conservazione fatture XML per 10 anni (obbligo fiscale)
   - Blocco login permanente

3. **Vantaggi:**
   - ✅ Rispetta GDPR Art.17
   - ✅ Rispetta obbligo fiscale D.P.R. 633/1972
   - ✅ Utente esercita diritto, azienda tutelata legalmente

**Opzione C - Disattivazione account:**
1. **Funzione "Disattiva account":**
   - Flag `is_active = false` su tabella users
   - Blocco login
   - Conservazione tutti dati (GDPR consente se legittimo interesse)
   - Utente può riattivare entro 90gg
   - Dopo 90gg: Anonimizzazione automatica

**Raccomandazione:** Implementare Opzione B (anonimizzazione) per bilanciare GDPR e obblighi fiscali.

**Timeline implementazione:** 2-3 giorni (form richiesta + workflow admin + anonimizzazione)

---

#### ❌ Diritto alla Portabilità (Art.20 GDPR)
**Stato:** MANCANTE - OBBLIGATORIO

**Descrizione Mancanza:**
Utente non può esportare dati in formato machine-readable per trasferirli ad altro servizio concorrente.

**Come Implementare:**
1. **Funzione "Esporta per portabilità":**
   - Diverso da Art.15 (quello è export leggibile umano)
   - Questo: Export ottimizzato per import in altri sistemi

2. **Formato export:**
   - JSON strutturato con schema definito
   - Include SOLO dati forniti dall'utente o generati automaticamente
   - ESCLUDE: Dati derivati da elaborazioni aziendali proprietarie (es. statistiche avanzate)

3. **Contenuto:**
   ```
   {
     "account": { "email": "...", "partita_iva": "...", ... },
     "ristoranti": [ { "nome": "...", "piva": "..." }, ... ],
     "fatture": [
       {
         "file": "base64_encoded_xml",
         "data": "2026-01-15",
         "fornitore": "...",
         "totale": 1234.56
       }
     ],
     "classificazioni": [ ... ]
   }
   ```

4. **Download:**
   - Pulsante "📤 Esporta dati per portabilità (JSON)"
   - File immediatamente scaricabile

**Timeline implementazione:** 1 giorno (è subset funzione Art.15)

---

#### ⚠️ Diritto di Rettifica (Art.16 GDPR)
**Stato:** PARZIALMENTE IMPLEMENTATO

**Descrizione Stato:**
Utente può modificare:
- ✅ Nome ristoranti/sedi
- ✅ Classificazioni manuali prodotti
- ❌ Email (NON modificabile)
- ❌ P.IVA (NON modificabile)
- ❌ Ragione sociale (NON modificabile)

**Come Implementare:**
1. **Sezione "Modifica dati account":**
   - Form con campi: Email, P.IVA, Ragione sociale
   - Validazione: Email unica, P.IVA formato corretto
   - Conferma password per modifiche sensibili
   - Invio email notifica post-modifica

2. **Limitazioni sicurezza:**
   - Cambio email: Invio link conferma a NUOVA email (verifica possesso)
   - Cambio P.IVA: Solo se nessuna fattura caricata (coerenza fiscale) OPPURE conferma admin

**Timeline implementazione:** 1-2 giorni (form + validazioni + conferme email)

---

### 2.3 SICUREZZA AVANZATA (PRIORITÀ MEDIA) 🟡

#### ⚠️ Autenticazione a Due Fattori (2FA/MFA)
**Stato:** MANCANTE - FORTEMENTE CONSIGLIATO PER ADMIN

**Descrizione Mancanza:**
Attualmente solo email + password. Se password compromessa → account compromesso.

**Come Implementare:**

**Opzione A - TOTP (Time-based One-Time Password):**
1. **Libreria:** pyotp (Python TOTP implementation)
2. **Flow attivazione:**
   - Utente abilita 2FA da "Impostazioni sicurezza"
   - Sistema genera secret TOTP
   - Mostra QR code da scansionare con Google Authenticator / Authy
   - Utente inserisce primo codice per conferma
   - Sistema salva `totp_secret` cifrato nel database

3. **Flow login:**
   - Dopo password corretta → Richiede codice 6 cifre
   - Validazione: pyotp verifica con secret utente
   - Codici backup: Genera 10 codici monouso per emergenze

4. **Obbligatorietà:**
   - Obbligatorio per account admin (`is_admin = true`)
   - Opzionale per clienti normali

**Opzione B - SMS OTP:**
1. **Pro:** Più user-friendly (no app)
2. **Contro:** Meno sicuro (SIM swapping), costoso (Twilio API)

**Opzione C - Email OTP:**
1. **Pro:** Gratuito, no app
2. **Contro:** MOLTO meno sicuro (email compromessa = account compromesso)

**Raccomandazione:** Implementare TOTP (Opzione A) - Bilanciamento sicurezza/usabilità ottimale.

**Conformità:**
- ✅ ENISA Guidelines on Secure Authentication (2020)
- ✅ PSD2 RTS on Strong Customer Authentication (se pagamenti)
- ✅ GDPR Art.32 (misure tecniche appropriate)

**Timeline implementazione:** 3-5 giorni (TOTP + UI + testing)

---

#### ⚠️ Rate Limiting e Protezione Brute-Force
**Stato:** PARZIALMENTE IMPLEMENTATO - NON ATTIVO

**Descrizione Stato:**
Campo `login_attempts` esiste nel database MA non è usato attivamente per bloccare tentativi.

**Come Implementare:**
1. **Contatore tentativi falliti:**
   - Incrementa `login_attempts` ad ogni login fallito
   - Reset a 0 su login riuscito
   
2. **Blocco temporaneo:**
   - Dopo 5 tentativi falliti: Blocco 15 minuti
   - Dopo 10 tentativi: Blocco 1 ora
   - Dopo 15 tentativi: Blocco 24 ore + notifica admin

3. **Captcha:**
   - Dopo 3 tentativi falliti: Mostra hCaptcha o reCAPTCHA
   - Previene bot automatizzati

4. **IP Rate Limiting:**
   - Middleware: Max 30 richieste/minuto per IP
   - Blocco IP sospetti (troppi tentativi multi-account)

5. **Notifiche:**
   - Email utente: "Rilevati tentativi accesso non autorizzati"
   - Email admin: "Account X sotto attacco brute-force"

**Conformità:**
- ✅ OWASP ASVS 2.2 - Authentication Verification
- ✅ GDPR Art.32.2 (capacità assicurare resilienza)

**Timeline implementazione:** 2-3 giorni (logica + captcha + email)

---

#### ⚠️ Log Retention e Backup Policy
**Stato:** INDETERMINATO - NON DOCUMENTATO

**Descrizione Mancanza:**
Sistema Supabase fa backup automatici (presumibilmente), ma non è documentato:
- Frequenza backup
- Durata retention backup
- Procedure restore
- Location geografica backup (UE vs extra-UE)

**Come Implementare:**
1. **Documentare policy attuale:**
   - Verificare con Supabase dashboard: backup schedule
   - Documentare in file `BACKUP_POLICY.md`

2. **Definire retention:**
   - Backup giornalieri: Conservazione 30 giorni
   - Backup mensili: Conservazione 12 mesi
   - Backup annuali: Conservazione 10 anni (obbligo fatture)

3. **Testing:**
   - Test restore mensile (disaster recovery drill)
   - Documentare RTO (Recovery Time Objective): max 4 ore
   - Documentare RPO (Recovery Point Objective): max 24 ore dati persi

4. **Notifiche:**
   - Alert automatico se backup fallisce
   - Email admin + dashboard notifica

**Conformità:**
- ✅ GDPR Art.32.1.c (capacità ripristinare dati)
- ✅ ISO/IEC 27001 - A.12.3.1 (backup informazioni)

**Timeline implementazione:** 1 giorno (documentazione) + test restore

---

#### ⚠️ Cifratura Email (TLS SMTP)
**Stato:** PROBABILMENTE IMPLEMENTATO - NON VERIFICATO

**Descrizione Incertezza:**
Email inviate via Brevo SMTP. Presumibilmente usa TLS, ma da verificare.

**Come Implementare:**
1. **Verifica configurazione:**
   - Controllare se porta SMTP è 587 (STARTTLS) o 465 (SSL/TLS)
   - Verificare certificato SSL Brevo valido

2. **Se NON configurato:**
   - Forzare `use_tls=True` in configurazione SMTP
   - Testare invio email con log connessione

3. **Documentare:**
   - Aggiungere in Privacy Policy: "Email protette da crittografia TLS 1.2+"

**Conformità:**
- ✅ GDPR Art.32.1.a (cifratura)
- ✅ Best practice email security

**Timeline implementazione:** 1 ora (verifica) / 2 ore (se da configurare)

---

### 2.4 MONITORING E COMPLIANCE (PRIORITÀ BASSA) 🟢

#### 🔵 Dashboard Sicurezza Admin
**Stato:** MANCANTE - NICE TO HAVE

**Descrizione Implementazione:**
Sezione admin panel dedicata a sicurezza:

1. **Statistiche:**
   - Tentativi login falliti ultimi 7 giorni (grafico)
   - Account con 2FA attivo (percentuale)
   - Account inattivi >90 giorni (lista)
   - Token reset password scaduti non usati

2. **Alerts:**
   - Account con >5 tentativi login falliti oggi
   - Fatture caricate con P.IVA mismatch (tentativi bloccati)

3. **Azioni rapide:**
   - Forza reset password account specifico
   - Blocca/sblocca account manualmente
   - Visualizza log accessi utente

**Timeline implementazione:** 3-4 giorni

---

#### 🔵 Notifiche Sicurezza Utente
**Stato:** MANCANTE - NICE TO HAVE

**Descrizione Implementazione:**
Email automatiche per eventi sicurezza:

1. **Login da nuovo dispositivo/IP:**
   - "Rilevato accesso da [IP] - [Città] il [data]"
   - Link "Non sei stato tu? Cambia password"

2. **Cambio password:**
   - "La tua password è stata modificata il [data]"
   - Link "Non sei stato tu? Recupera account"

3. **Cambio email:**
   - Email a VECCHIA email: "Email account modificata"
   - Email a NUOVA email: "Conferma possesso email"

**Timeline implementazione:** 2 giorni

---

#### 🔵 Penetration Testing / Security Audit
**Stato:** MAI ESEGUITO (PRESUMIBILMENTE)

**Descrizione Implementazione:**
1. **Audit interno:**
   - Checklist OWASP Top 10 2021
   - Test SQL Injection (RLS effettivo?)
   - Test XSS su form input
   - Test CSRF token Streamlit

2. **Audit esterno:**
   - Assumere security consultant
   - Penetration test black-box
   - Report vulnerabilità + remediation plan

**Timeline implementazione:** 1 settimana (interno) / 2-4 settimane (esterno)

---

## 📋 PARTE 3: PIANO DI IMPLEMENTAZIONE PRIORITIZZATO

### FASE 1 - CONFORMITÀ LEGALE MINIMA (1-2 SETTIMANE) 🔴

**Obiettivo:** Essere legalmente deployment-ready

| ID | Task | Giorni | Responsabile | Deliverable |
|----|------|--------|--------------|-------------|
| 1.1 | Redazione Privacy Policy Art.13 GDPR | 2 | Legale | Documento + revisione avvocato |
| 1.2 | Integrazione Privacy Policy in UI | 1 | Developer | Link sidebar + popup testo |
| 1.3 | Checkbox consenso registrazione | 0.5 | Developer | Form registrazione modificato |
| 1.4 | Verifica cookie + eventuale banner | 1 | Developer | Analisi + implementazione |
| 1.5 | Redazione Termini e Condizioni | 2 | Legale | Documento T&C |
| 1.6 | Integrazione T&C in UI | 0.5 | Developer | Link + checkbox |
| 1.7 | Compilazione Registro Trattamenti | 1 | DPO/Titolare | File Excel interno |

**Totale Fase 1:** 8 giorni lavorativi

---

### FASE 2 - DIRITTI UTENTE (1 SETTIMANA) 🟠

**Obiettivo:** GDPR Art.15-17-20 completi

| ID | Task | Giorni | Responsabile | Deliverable |
|----|------|--------|--------------|-------------|
| 2.1 | Funzione "Esporta tutti i miei dati" | 1.5 | Developer | Pulsante + export ZIP |
| 2.2 | Funzione "Richiedi cancellazione account" | 2 | Developer | Form + workflow admin |
| 2.3 | Logica anonimizzazione post-cancellazione | 1 | Developer | Script SQL + testing |
| 2.4 | Funzione "Esporta per portabilità JSON" | 0.5 | Developer | Subset funzione 2.1 |
| 2.5 | Form modifica email/P.IVA/Ragione sociale | 1 | Developer | UI + validazioni |
| 2.6 | Email conferma modifiche dati | 1 | Developer | Template + invio |

**Totale Fase 2:** 7 giorni lavorativi

---

### FASE 3 - SICUREZZA AVANZATA (2 SETTIMANE) 🟡

**Obiettivo:** Resilienza attacchi

| ID | Task | Giorni | Responsabile | Deliverable |
|----|------|--------|--------------|-------------|
| 3.1 | Implementazione TOTP 2FA | 3 | Developer | QR code + validazione |
| 3.2 | 2FA obbligatorio per admin | 0.5 | Developer | Check is_admin |
| 3.3 | Rate limiting login attempts | 2 | Developer | Logica blocco + testing |
| 3.4 | Integrazione hCaptcha dopo 3 tentativi | 1 | Developer | Form login + validazione |
| 3.5 | Email notifiche tentativi sospetti | 1 | Developer | Template + trigger |
| 3.6 | Verifica TLS email (Brevo) | 0.5 | Developer | Test + documentazione |
| 3.7 | Documentazione backup policy | 1 | DevOps | File BACKUP_POLICY.md |
| 3.8 | Test restore backup | 1 | DevOps | Drill + report |

**Totale Fase 3:** 10 giorni lavorativi

---

### FASE 4 - MONITORING E MIGLIORAMENTI (1 SETTIMANA) 🟢

**Obiettivo:** Visibilità e proattività

| ID | Task | Giorni | Responsabile | Deliverable |
|----|------|--------|--------------|-------------|
| 4.1 | Dashboard sicurezza admin panel | 3 | Developer | Tab nuova + statistiche |
| 4.2 | Notifiche login nuovo dispositivo | 1.5 | Developer | Email automatiche |
| 4.3 | Notifiche cambio password/email | 1 | Developer | Email automatiche |
| 4.4 | OWASP Top 10 checklist interna | 2 | Security | Report + fixing |

**Totale Fase 4:** 7.5 giorni lavorativi

---

### FASE 5 - AUDIT ESTERNO (OPZIONALE) 🔵

**Obiettivo:** Certificazione sicurezza

| ID | Task | Settimane | Responsabile | Deliverable |
|----|------|-----------|--------------|-------------|
| 5.1 | Selezione vendor penetration test | 1 | Management | Contratto firmato |
| 5.2 | Penetration test black-box | 2 | Vendor | Report vulnerabilità |
| 5.3 | Remediation vulnerabilità critiche | 2 | Developer | Patch + retest |
| 5.4 | Report finale compliance | 1 | Vendor | Certificazione |

**Totale Fase 5:** 6 settimane (1.5 mesi)

---

## 🎯 TIMELINE COMPLESSIVO

### Scenario Minimum Viable Compliance (MVC):
**Fasi 1 + 2:** 3 settimane (15 giorni lavorativi)
- ✅ Conformità GDPR documentale
- ✅ Diritti utente implementati
- ✅ Deploy commerciale possibile

### Scenario Full Compliance:
**Fasi 1 + 2 + 3:** 5 settimane (25 giorni lavorativi)
- ✅ MVC + sicurezza avanzata (2FA, rate limiting)
- ✅ Deploy enterprise-ready

### Scenario Gold Standard:
**Fasi 1 + 2 + 3 + 4 + 5:** 3 mesi
- ✅ Full compliance + monitoring + audit esterno
- ✅ Certificazione sicurezza da esibire clienti

---

## 💰 STIMA COSTI IMPLEMENTAZIONE

### Risorse Umane:
| Ruolo | Giorni | Tariffa/Giorno | Costo |
|-------|--------|----------------|-------|
| **Developer Senior** | 25gg | €400 | €10.000 |
| **Avvocato Privacy** | 3gg | €600 | €1.800 |
| **DPO/Consulente GDPR** | 2gg | €500 | €1.000 |
| **Security Auditor** (opz.) | 10gg | €800 | €8.000 |

**Totale Risorse:** €12.800 (MVC) / €20.800 (con audit)

### Software/Servizi:
| Servizio | Costo Mensile | Costo Setup |
|----------|---------------|-------------|
| hCaptcha Enterprise | €0 (free tier) | €0 |
| TOTP (pyotp) | €0 (open source) | €0 |
| Privacy Policy Generator | €0-50 (template) | €50 |
| Penetration Test | - | €5.000-15.000 |

**Totale Software:** €50 (MVC) / €10.000 (con pentest)

### TOTALE PROGETTO:
- **MVC (Fasi 1-2):** €12.850
- **Full Compliance (Fasi 1-3):** €12.850
- **Gold Standard (Fasi 1-5):** €30.850

---

## 🚨 RACCOMANDAZIONI PRIORITARIE

### DA FARE SUBITO (PRIMA DI DEPLOY PRODUZIONE):
1. ✅ **Privacy Policy + T&C** - Obbligatori per legge
2. ✅ **Funzione cancellazione account** - GDPR Art.17 non negoziabile
3. ✅ **Registro trattamenti** - Compliance interna
4. ✅ **Export dati utente** - GDPR Art.15 non negoziabile

### DA FARE APPENA POSSIBILE:
1. ✅ **2FA per admin** - Riduce rischio compromissione massiva
2. ✅ **Rate limiting** - Previene attacchi automatizzati
3. ✅ **Backup policy documentata** - Business continuity

### NICE TO HAVE (POST-LAUNCH):
1. 🔵 Dashboard sicurezza admin
2. 🔵 Notifiche login nuovo dispositivo
3. 🔵 Audit esterno

---

## 📞 CONTATTI E RISORSE

### Riferimenti Normativi:
- **GDPR Testo Completo:** https://gdpr-info.eu/
- **Garante Privacy Italia:** https://www.garanteprivacy.it/
- **OWASP Top 10:** https://owasp.org/Top10/
- **ENISA Guidelines:** https://www.enisa.europa.eu/

### Tool Consigliati:
- **Privacy Policy Generator:** iubenda.com, freeprivacypolicy.com
- **TOTP Library:** pyotp (Python)
- **Captcha:** hCaptcha (privacy-friendly), reCAPTCHA v3
- **Penetration Testing:** Hackerone, Bugcrowd, società locali

### Consulenti Consigliati:
- **Avvocato Privacy:** Cercare specializzato GDPR + tech
- **DPO Certificato:** IAPP CIPP/E o CIPM
- **Security Auditor:** OSCP, CEH, CISSP certificati

---

## 📝 NOTE FINALI

Questo documento è un'analisi tecnico-legale basata sul codice sorgente attuale. 

**Disclaimer:**
- Non costituisce consulenza legale vincolante
- Per deploy produzione: Far revisionare da avvocato specializzato privacy
- Normativa in evoluzione: Aggiornare annualmente

**Prossimi Passi:**
1. Condividere questo documento con management
2. Ottenere budget per Fase 1 (MVC)
3. Contattare avvocato privacy per Privacy Policy
4. Schedulare sprint development per implementazioni

**Documento Creato Da:** GitHub Copilot (AI Assistant)  
**Data:** 3 Febbraio 2026  
**Versione:** 1.0

---

## 📊 ALLEGATO: CHECKLIST CONFORMITÀ

### GDPR Articles Checklist:

- [ ] **Art.5** - Principi trattamento → Privacy Policy documenta
- [ ] **Art.6** - Base giuridica → Contratto esecuzione
- [ ] **Art.7** - Consenso → Checkbox registrazione
- [ ] **Art.13** - Informativa → Privacy Policy completa
- [x] **Art.15** - Accesso → PARZIALE (serve export)
- [ ] **Art.16** - Rettifica → Da implementare form modifica
- [ ] **Art.17** - Cancellazione → MANCANTE (priorità alta)
- [ ] **Art.20** - Portabilità → MANCANTE
- [ ] **Art.25** - Privacy by design → RLS implementato ✅
- [ ] **Art.30** - Registro → Da compilare
- [x] **Art.32** - Sicurezza → SOLIDO (Argon2, RLS) ✅
- [ ] **Art.33** - Notifica breach → Procedura da documentare
- [ ] **Art.37** - DPO → Non obbligatorio se <250 dip

### OWASP Top 10:2021 Checklist:

- [x] **A01 - Broken Access Control** → RLS PostgreSQL ✅
- [x] **A02 - Cryptographic Failures** → Argon2 + secrets.toml ✅
- [ ] **A03 - Injection** → Da testare SQL injection
- [x] **A04 - Insecure Design** → Privacy by design OK ✅
- [ ] **A05 - Security Misconfiguration** → Da verificare Supabase settings
- [x] **A06 - Vulnerable Components** → Da monitorare (pip-audit)
- [x] **A07 - Authentication Failures** → Argon2 OK, serve 2FA
- [ ] **A08 - Software Data Integrity** → Da implementare integrity check upload
- [ ] **A09 - Logging Failures** → Logger OK, serve retention policy
- [ ] **A10 - SSRF** → Non applicabile (no fetch URL utente)

---

**Fine Documento**
