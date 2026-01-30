# 💻 COMANDI UTILI - Pannello Admin

## 🚀 AVVIO APPLICAZIONE

### Sviluppo Locale
```bash
# Avvia app principale
streamlit run app.py

# Avvia direttamente il pannello admin (richiede login)
streamlit run pages/admin.py
```

### Test
```bash
# Test configurazione pannello admin
python test_admin_panel.py

# Test invio email Brevo
python test_brevo.py

# Test connessione Supabase
python test_supabase.py
```

---

## 📦 INSTALLAZIONE DIPENDENZE

```bash
# Installazione completa da requirements.txt
pip install -r requirements.txt

# Installazione pacchetti specifici per admin panel
pip install streamlit
pip install extra-streamlit-components
pip install supabase
pip install argon2-cffi
pip install requests
pip install pandas
```

---

## 🗄️ GESTIONE DATABASE (SUPABASE)

### Query Utili (Supabase SQL Editor)

#### Lista tutti gli utenti
```sql
SELECT 
    email, 
    nome_ristorante, 
    piano, 
    ruolo, 
    attivo, 
    created_at 
FROM users 
ORDER BY created_at DESC;
```

#### Conta utenti per ruolo
```sql
SELECT 
    ruolo, 
    COUNT(*) as totale,
    SUM(CASE WHEN attivo THEN 1 ELSE 0 END) as attivi
FROM users 
GROUP BY ruolo;
```

#### Trova clienti disattivi
```sql
SELECT email, nome_ristorante, created_at 
FROM users 
WHERE attivo = false 
AND ruolo = 'cliente'
ORDER BY created_at DESC;
```

#### Ultimi login
```sql
SELECT 
    email, 
    nome_ristorante, 
    last_login 
FROM users 
WHERE last_login IS NOT NULL 
ORDER BY last_login DESC 
LIMIT 10;
```

#### Clienti creati oggi
```sql
SELECT email, nome_ristorante, piano 
FROM users 
WHERE DATE(created_at) = CURRENT_DATE 
AND ruolo = 'cliente';
```

#### Reset password scadute (pulizia)
```sql
UPDATE users 
SET reset_code = NULL, reset_expires = NULL 
WHERE reset_expires < NOW();
```

#### Elimina utente (ATTENZIONE!)
```sql
-- ⚠️ ATTENZIONE: Azione irreversibile!
DELETE FROM users 
WHERE email = 'cliente@example.com';
```

#### Crea backup utenti
```sql
-- Copia tabella users per backup
CREATE TABLE users_backup AS 
SELECT * FROM users;
```

---

## 🔐 GESTIONE ADMIN

### Aggiungi Nuovo Admin Manualmente

**Opzione 1: Modifica Codice (Consigliato)**
```python
# File: app.py (linea ~650)
ADMIN_EMAILS = [
    "mattiadavolio90@gmail.com",
    "nuovo.admin@example.com"  # ← Aggiungi qui
]

# File: pages/admin.py (linea ~20)
ADMIN_EMAILS = [
    "mattiadavolio90@gmail.com",
    "nuovo.admin@example.com"  # ← Aggiungi qui
]
```

**Opzione 2: Crea Admin via Script**
```bash
python create_admin_argon2.py
```

Modifica nel file:
```python
EMAIL_ADMIN = "nuovo.admin@example.com"
PASSWORD_ADMIN = "PasswordSicura123!"
NOME_RISTORANTE = "Admin 2"
```

---

## 📧 GESTIONE EMAIL (BREVO)

### Test Invio Email
```bash
python test_brevo.py
```

### Verifica API Key
```bash
curl -X GET "https://api.brevo.com/v3/account" \
  -H "api-key: xkeysib-..."
```

### Statistiche Email (richiede jq)
```bash
curl -X GET "https://api.brevo.com/v3/smtp/statistics/events?limit=10" \
  -H "api-key: xkeysib-..." | jq
```

---

## 📊 MONITORAGGIO E LOG

### Visualizza Log in Tempo Reale

**Windows (PowerShell)**
```powershell
# Log admin
Get-Content admin.log -Wait -Tail 20

# Log app
Get-Content app.log -Wait -Tail 20

# Log debug
Get-Content debug.log -Wait -Tail 20
```

**Linux/Mac**
```bash
# Log admin
tail -f admin.log

# Log app  
tail -f app.log

# Log debug
tail -f debug.log
```

### Cerca Errori nei Log

**Windows (PowerShell)**
```powershell
# Cerca errori in admin.log
Select-String -Path admin.log -Pattern "ERROR|Exception|Errore"

# Cerca operazioni specifiche
Select-String -Path admin.log -Pattern "Password resettata"

# Conta operazioni per tipo
(Select-String -Path admin.log -Pattern "Cliente creato").Count
```

**Linux/Mac**
```bash
# Cerca errori
grep -E "ERROR|Exception|Errore" admin.log

# Conta operazioni
grep -c "Cliente creato" admin.log
```

### Pulizia Log

**Windows (PowerShell)**
```powershell
# Backup log prima di pulire
Copy-Item admin.log admin.log.backup

# Svuota log (mantiene file)
Clear-Content admin.log
Clear-Content app.log
Clear-Content debug.log
```

**Linux/Mac**
```bash
# Backup
cp admin.log admin.log.backup

# Svuota
> admin.log
> app.log
> debug.log
```

---

## 🔧 CONFIGURAZIONE SECRETS

### Struttura File secrets.toml
```bash
# Percorso
.streamlit/secrets.toml

# Crea directory se non esiste (Windows PowerShell)
New-Item -ItemType Directory -Force -Path .streamlit

# Copia template
Copy-Item secrets.toml.example .streamlit/secrets.toml

# Modifica con editor
notepad .streamlit/secrets.toml  # Windows
nano .streamlit/secrets.toml     # Linux/Mac
```

### Verifica Secrets Caricati
```python
import streamlit as st

# Test in Python interattivo o script
print(st.secrets["supabase"]["url"])
print(st.secrets["brevo"]["api_key"][:20] + "...")
print(st.secrets["app"]["url"])
```

---

## 🌐 DEPLOY STREAMLIT CLOUD

### Deploy da Repository Git
```bash
# 1. Inizializza Git (se non già fatto)
git init

# 2. Aggiungi .gitignore
echo ".streamlit/secrets.toml" >> .gitignore
echo "__pycache__/" >> .gitignore
echo "*.log" >> .gitignore
echo "*.pyc" >> .gitignore

# 3. Commit codice
git add .
git commit -m "Implementato pannello admin"

# 4. Push su GitHub
git remote add origin https://github.com/tuo-username/tuo-repo.git
git branch -M main
git push -u origin main
```

### Configura Secrets su Streamlit Cloud
1. Vai su https://share.streamlit.io
2. Seleziona la tua app
3. Settings → Secrets
4. Copia contenuto `.streamlit/secrets.toml`
5. Incolla e salva

---

## 🧪 TEST FUNZIONALITÀ

### Test Completo Automatizzato
```bash
# Esegui tutti i test
python test_admin_panel.py
```

### Test Manuali Checklist

```bash
# 1. Test Login Admin
streamlit run app.py
# Login con email admin → Verificare pulsante "Pannello Admin" visibile

# 2. Test Creazione Cliente
# Pannello Admin → Crea Cliente → Verificare email ricevuta

# 3. Test Login Cliente
# Logout → Login con credenziali cliente → Verificare accesso

# 4. Test Cambio Password
# Come cliente → Cambio Password → Logout → Re-login con nuova password

# 5. Test Reset Password Admin
# Come admin → Gestione Clienti → Reset Password → Verificare email

# 6. Test Attiva/Disattiva
# Come admin → Disattiva cliente → Logout → Tentare login cliente (deve fallire)
# Come admin → Riattiva cliente → Logout → Tentare login cliente (deve funzionare)
```

---

## 📈 PERFORMANCE E MANUTENZIONE

### Backup Database
```bash
# Esporta dati Supabase (tramite dashboard)
# Supabase Dashboard → Database → Exports → CSV

# Oppure via script Python
python -c "
from supabase import create_client
import streamlit as st
import pandas as pd

supabase = create_client(st.secrets['supabase']['url'], st.secrets['supabase']['key'])
response = supabase.table('users').select('*').execute()
df = pd.DataFrame(response.data)
df.to_csv('backup_users.csv', index=False)
print('Backup creato: backup_users.csv')
"
```

### Ottimizzazione
```bash
# Pulisci cache Streamlit
streamlit cache clear

# Riavvia con cache pulita
streamlit run app.py --server.runOnSave=true
```

---

## 🐛 DEBUG E TROUBLESHOOTING

### Debug Mode
```bash
# Avvia con log verboso
streamlit run app.py --logger.level=debug
```

### Verifica Connessioni

**Test Supabase**
```bash
python test_supabase.py
```

**Test Brevo**
```bash
python test_brevo.py
```

**Test Import**
```python
# Test veloce import librerie
python -c "
import streamlit as st
import extra_streamlit_components as stx
from supabase import create_client
from argon2 import PasswordHasher
import requests
print('✅ Tutti i moduli importati correttamente')
"
```

### Rebuild Secrets
```bash
# Se secrets non funzionano, ricrea file
rm -rf .streamlit/secrets.toml          # Linux/Mac
Remove-Item .streamlit/secrets.toml     # Windows PowerShell

# Ricopia da template
cp secrets.toml.example .streamlit/secrets.toml
```

---

## 🔄 AGGIORNAMENTI

### Pull Nuove Modifiche
```bash
git pull origin main
pip install -r requirements.txt
streamlit run app.py
```

### Verifica Versione
```bash
# Streamlit
streamlit --version

# Python
python --version

# Librerie specifiche
pip show streamlit
pip show supabase
pip show argon2-cffi
```

---

## 📝 UTILITY SCRIPTS

### Genera Password Manualmente
```python
python -c "
import secrets
import string

def genera_password(lunghezza=12):
    caratteri = string.ascii_letters + string.digits + '!@#$%&*'
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice('!@#$%&*')
    ]
    password += [secrets.choice(caratteri) for _ in range(lunghezza - 4)]
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)

for i in range(5):
    print(f'Password {i+1}: {genera_password()}')
"
```

### Hash Password Manualmente
```python
python -c "
from argon2 import PasswordHasher

ph = PasswordHasher()
password = input('Inserisci password da hashare: ')
hash_pwd = ph.hash(password)
print(f'\nHash Argon2:\n{hash_pwd}')
"
```

### Conta Clienti
```python
python -c "
import streamlit as st
from supabase import create_client

supabase = create_client(st.secrets['supabase']['url'], st.secrets['supabase']['key'])
response = supabase.table('users').select('ruolo', count='exact').execute()

print(f'Totale utenti: {response.count}')
"
```

---

## 🎯 SHORTCUTS UTILI

### Windows (PowerShell)
```powershell
# Alias per avvio rapido
function Start-App { streamlit run app.py }
function Start-Admin { streamlit run pages/admin.py }
function Test-Admin { python test_admin_panel.py }
function Show-Logs { Get-Content admin.log -Wait -Tail 20 }

# Usa con:
Start-App
Start-Admin
Test-Admin
Show-Logs
```

### Linux/Mac (Bash)
```bash
# Aggiungi a ~/.bashrc o ~/.zshrc
alias fcstart='streamlit run app.py'
alias fcadmin='streamlit run pages/admin.py'
alias fctest='python test_admin_panel.py'
alias fclogs='tail -f admin.log'

# Ricarica configurazione
source ~/.bashrc  # o ~/.zshrc

# Usa con:
fcstart
fcadmin
fctest
fclogs
```

---

## 📞 SUPPORTO

### File da Controllare in Caso di Problemi
1. `admin.log` - Log operazioni admin
2. `app.log` - Log applicazione generale
3. `debug.log` - Log debug dettagliato
4. `.streamlit/secrets.toml` - Configurazione

### Comandi Diagnostici Rapidi
```bash
# Check completo sistema
python test_admin_panel.py

# Verifica file esistenti
ls pages/admin.py pages/cambio_password.py

# Verifica secrets
python -c "import streamlit as st; print('✅ Secrets OK')" 2>&1
```

---

**© 2025 Analisi Fatture AI - Comandi Utili**
