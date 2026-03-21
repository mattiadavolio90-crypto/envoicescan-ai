# Procedura di Migrazione FCI_PROJECT su Nuovo PC

> **Documento operativo** — Segui i passi nell'ordine indicato.  
> Tempo stimato: 15–30 minuti (escluso download Python/VS Code).

---

## Prerequisiti sul nuovo PC

| Software | Versione | Download |
|----------|----------|----------|
| Python | **3.12.x** | https://www.python.org/downloads/ |
| VS Code | ultima stabile | https://code.visualstudio.com/ |
| Git (opzionale) | ultima stabile | https://git-scm.com/ |

> ⚠️ Durante l'installazione di Python, **spunta "Add Python to PATH"**.

---

## STEP 1 — Copia i file del progetto

### Cosa copiare (USB / Google Drive / altro)

Copia l'intera cartella `FCI_PROJECT` **escludendo** le seguenti cartelle inutili:

| Cartella da ESCLUDERE | Motivo |
|-----------------------|--------|
| `.venv/` | ~16.000 file — si ricrea in automatico |
| `__pycache__/` | file compilati temporanei |
| `.pytest_cache/` | cache dei test |
| `.git/` | storia git (opzionale escluderla) |

### Struttura minima da copiare

```
FCI_PROJECT/
├── app.py
├── requirements.txt
├── pytest.ini
├── pages/
├── services/
├── components/
├── config/
├── utils/
├── tests/
├── static/
├── migrations/
├── DOCUMENTAZIONE/
├── .streamlit/
│   ├── secrets.toml        ← ⚠️ FILE CRITICO (contiene le chiavi API)
│   └── config.toml
└── .devcontainer/          (opzionale)
```

> 🔑 **`secrets.toml` è il file più importante.** Senza di esso l'app non si connette
> a Supabase, OpenAI o Brevo. Non va mai caricato su GitHub.

---

## STEP 2 — Installa Python 3.12

1. Scarica Python 3.12.x da https://www.python.org/downloads/
2. Durante l'installazione **seleziona "Add python.exe to PATH"**
3. Verifica l'installazione aprendo PowerShell:
   ```powershell
   python --version
   # Deve mostrare: Python 3.12.x
   ```

---

## STEP 3 — Crea l'ambiente virtuale

Apri PowerShell nella cartella del progetto:

```powershell
cd C:\Users\<TUO_UTENTE>\Desktop\FCI_PROJECT

# Crea ambiente virtuale
python -m venv .venv

# Attiva ambiente virtuale
.\.venv\Scripts\Activate.ps1
```

> Se PowerShell blocca l'esecuzione degli script, esegui prima:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

---

## STEP 4 — Installa le dipendenze

Con il `.venv` attivo (vedi `(.venv)` all'inizio del prompt):

```powershell
pip install -r requirements.txt
```

Le librerie installate sono:

| Libreria | Uso |
|----------|-----|
| `streamlit` | Framework interfaccia web |
| `supabase` | Connessione al database cloud |
| `openai` | Categorizzazione AI |
| `pandas` | Elaborazione dati/fatture |
| `PyMuPDF` | Lettura file PDF |
| `openpyxl` | Export Excel |
| `argon2-cffi` | Hash password |
| `sib-api-v3-sdk` (Brevo) | Invio email |
| `plotly` | Grafici |
| `tenacity` | Retry automatico connessioni |

> Il download può richiedere 3–5 minuti.

---

## STEP 5 — Verifica il file secrets.toml

Controlla che il file `.streamlit/secrets.toml` sia presente e contenga:

```toml
OPENAI_API_KEY = "sk-..."

[supabase]
url = "https://xxxx.supabase.co"
key = "eyJ..."

[brevo]
api_key = "xkeysib-..."
sender_email = "..."
sender_name = "..."

[app]
url = "http://localhost:8501"
```

> Se il file manca o è incompleto, recupera una copia dal PC precedente
> oppure dai pannelli di controllo dei rispettivi servizi:
> - **Supabase** → https://supabase.com → Project Settings → API
> - **OpenAI** → https://platform.openai.com/api-keys
> - **Brevo** → https://app.brevo.com → SMTP & API

---

## STEP 6 — Configura VS Code

1. Apri VS Code
2. Installa le estensioni consigliate:
   - **Python** (Microsoft)
   - **GitHub Copilot** (se disponibile)
3. Apri la cartella del progetto: `File → Open Folder → FCI_PROJECT`
4. Seleziona l'interprete Python: `Ctrl+Shift+P` → "Python: Select Interpreter" → scegli `.venv`

---

## STEP 7 — Avvia l'app e verifica

```powershell
# Assicurati di essere nella cartella giusta con .venv attivo
cd C:\Users\<TUO_UTENTE>\Desktop\FCI_PROJECT
.\.venv\Scripts\Activate.ps1

# Avvia l'app
streamlit run app.py
```

Il browser si apre automaticamente su `http://localhost:8501`.

### Checklist verifica funzionamento

- [ ] Login funzionante (connessione Supabase OK)
- [ ] Dashboard carica i dati
- [ ] Upload PDF/XML funzionante
- [ ] Categorizzazione AI funzionante (OpenAI OK)
- [ ] Invio email funzionante (Brevo OK)

---

## STEP 8 — Esegui i test (opzionale ma consigliato)

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ --tb=short
# Atteso: 172 passed, 0 failed
```

---

## Risoluzione problemi comuni

| Problema | Soluzione |
|----------|-----------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` con `.venv` attivo |
| `secrets.toml not found` | Copia il file in `.streamlit/secrets.toml` |
| `ExecutionPolicy` error PowerShell | `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| App si apre ma non carica dati | Controlla chiavi Supabase in `secrets.toml` |
| Errore OpenAI | Controlla `OPENAI_API_KEY` in `secrets.toml` |
| `.venv\Scripts\Activate.ps1` non trovato | Ricrea il venv: `python -m venv .venv` |
| Port 8501 già occupato | `streamlit run app.py --server.port 8502` |

---

## Note per uso con Avvia App.bat

Il file `Avvia App.bat` nella cartella del progetto automatizza l'avvio.
Aprilo con Notepad e verifica che il percorso Python punti al `.venv` locale:

```bat
.\.venv\Scripts\python.exe -m streamlit run app.py
```

---

*Documento generato il 20/03/2026 — versione progetto con 172 test passati.*
