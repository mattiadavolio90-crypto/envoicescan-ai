# 🔧 Pannello Amministrazione - Analisi Fatture AI

## 📋 Panoramica

Sistema completo di gestione clienti per amministratori. Permette di creare account in modo automatizzato senza mai dover gestire manualmente password o hash.

## 🎯 Funzionalità Principali

### ✅ Creazione Cliente Automatizzata
- **Input richiesto:** Solo email e nome ristorante
- **Processo automatico:**
  1. Generazione password sicura (12 caratteri: lettere, numeri, simboli)
  2. Hash automatico con Argon2
  3. Salvataggio su Supabase
  4. Invio email professionale con credenziali via Brevo

### 👥 Gestione Clienti
- **Visualizzazione completa:** Lista tutti i clienti con informazioni dettagliate
- **Ricerca intelligente:** Filtra per email o nome ristorante
- **Azioni disponibili:**
  - 🔄 **Reset Password:** Genera nuova password e invia email automaticamente
  - ✅ **Attiva Account:** Riattiva clienti disattivati
  - 🚫 **Disattiva Account:** Blocca l'accesso temporaneamente (senza eliminare dati)

## 🔒 Sicurezza

### Controlli di Accesso
1. **Verifica Login:** Controlla che l'utente sia autenticato
2. **Verifica Admin:** Solo email nella whitelist possono accedere
3. **Redirect automatico:** Utenti non autorizzati vengono reindirizzati

### Lista Admin
Modificabile in due punti (devono coincidere):
- `pages/admin.py` → `ADMIN_EMAILS`
- `app.py` → `ADMIN_EMAILS`

```python
ADMIN_EMAILS = [
    "mattiadavolio90@gmail.com",
    # Aggiungi altri admin qui
]
```

## 📧 Template Email

Le email inviate ai clienti includono:
- 🎨 Design professionale e responsive
- 🔑 Credenziali formattate chiaramente
- 🔗 Link diretto all'applicazione
- ⚠️ Avvisi di sicurezza
- 📝 Guida alle funzionalità principali

**Configurazione URL App:**
Nel file `.streamlit/secrets.toml`:
```toml
[app]
url = "https://tuaapp.streamlit.app"
```

## 🚀 Come Utilizzare

### 1. Accesso al Pannello
- Effettua login come admin
- Clicca sul pulsante **"🔧 Pannello Admin"** nell'header
- Solo gli admin vedranno questo pulsante

### 2. Creare un Nuovo Cliente
1. Vai alla tab **"➕ Crea Nuovo Cliente"**
2. Compila i campi:
   - **Email Cliente:** indirizzo email per il login
   - **Nome Ristorante:** nome dell'attività
   - **Piano:** base / premium / enterprise
3. Clicca **"🚀 Crea Account e Invia Email"**
4. Il sistema:
   - Crea l'account
   - Genera password sicura
   - Invia email automaticamente
   - Mostra conferma

### 3. Gestire Clienti Esistenti
1. Vai alla tab **"👥 Gestione Clienti"**
2. Usa la barra di ricerca per filtrare
3. Per ogni cliente puoi:
   - **Reset Password:** Genera nuova password e invia email
   - **Attiva/Disattiva:** Controlla l'accesso all'app

## 🔧 Configurazione Tecnica

### Requisiti
- Python 3.8+
- Librerie (già in requirements.txt):
  ```
  streamlit
  extra-streamlit-components
  supabase
  argon2-cffi
  requests
  pandas
  ```

### Secrets Necessari
File `.streamlit/secrets.toml`:
```toml
# Brevo (Email Service)
[brevo]
api_key = "xkeysib-..."
sender_email = "contact@updates.brevo.com"
sender_name = "Analisi Fatture AI"

# Supabase (Database)
[supabase]
url = "https://xxx.supabase.co"
key = "eyJhbGc..."

# App URL (per email)
[app]
url = "https://tuaapp.streamlit.app"
```

### Struttura Database (Supabase)

Tabella `users`:
```sql
- id: UUID (primary key)
- email: TEXT (unique)
- password_hash: TEXT
- nome_ristorante: TEXT
- piano: TEXT (base/premium/enterprise)
- ruolo: TEXT (admin/cliente)
- attivo: BOOLEAN
- created_at: TIMESTAMP
- last_login: TIMESTAMP
- reset_code: TEXT (nullable)
- reset_expires: TIMESTAMP (nullable)
```

## 📊 Logging

Il pannello admin mantiene un log separato:
- **File:** `admin.log`
- **Registra:**
  - Creazioni account
  - Reset password
  - Modifiche stato attivo
  - Tentativi di accesso non autorizzati
  - Errori di sistema

## ⚠️ Best Practices

### Sicurezza
- ✅ Non mostrare mai le password nell'interfaccia
- ✅ Le password vengono inviate solo via email
- ✅ Log di tutte le azioni sensibili
- ✅ Controllo accesso multi-livello

### Gestione Clienti
- 📧 Verifica sempre l'email prima di creare account
- 🔄 Usa "Reset Password" invece di modificare manualmente
- 🚫 Preferisci "Disattiva" invece di eliminare account
- 📝 Mantieni traccia delle comunicazioni con i clienti

### Email
- ✅ Testa l'invio email prima di creare clienti in produzione
- ✅ Configura correttamente l'URL dell'app
- ✅ Verifica che le email non vadano in spam

## 🐛 Troubleshooting

### "Configurazione email mancante"
- Verifica che `[brevo]` sia presente in `secrets.toml`
- Controlla che `api_key` sia valida

### "Email già registrata"
- Il cliente esiste già nel database
- Usa la funzione "Reset Password" invece di ricreare

### "Errore invio email"
- Verifica credenziali Brevo
- Controlla log in `admin.log`
- Testa con `test_brevo.py`

### Pulsante Admin non visibile
- Verifica di essere loggato con email admin
- Controlla che `ADMIN_EMAILS` contenga la tua email
- Liste in `app.py` e `pages/admin.py` devono coincidere

## 📈 Metriche e Monitoraggio

Il pannello mostra:
- **Totale clienti:** Numero totale account
- **Status:** Attivi vs Disattivi (con indicatori colorati)
- **Piano:** Distribuzione per tipo di abbonamento
- **Data creazione:** Quando è stato registrato ogni cliente

## 🔮 Sviluppi Futuri

Possibili miglioramenti:
- [ ] Dashboard con statistiche aggregate
- [ ] Export lista clienti in CSV/Excel
- [ ] Notifiche email automatiche (es: scadenza abbonamento)
- [ ] Gestione multipla (azioni su più clienti)
- [ ] Log attività cliente (ultimo accesso, fatture processate)
- [ ] Gestione ruoli personalizzati
- [ ] Integrazione pagamenti (Stripe/PayPal)

## 📞 Supporto

Per problemi o domande:
- 📝 Controlla `admin.log` per errori
- 🔍 Verifica configurazione in `secrets.toml`
- 💬 Contatta il team di sviluppo

---

**© 2025 Analisi Fatture AI - Pannello Amministrazione**
