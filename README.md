#  OH YEAH! Hub - Gestione Costi Ristorante

**Versione:** 4.0  
**Status:**  Produzione  
**Ultimo aggiornamento:** Marzo 2026

---

##  Descrizione

Piattaforma SaaS per la gestione automatizzata dei costi di ristoranti e attività food & beverage.  
Analizza fatture elettroniche (XML, P7M, PDF), categorizza i prodotti con intelligenza artificiale e genera report dettagliati su margini e spese.

---

##  Funzionalità

- Analisi automatica fatture XML/P7M/PDF
- Categorizzazione prodotti con AI (OpenAI GPT-4o-mini)
- Dashboard margini mensili (Food, Beverage, Spese Generali)
- Confronto prezzi fornitori
- Gestione multi-ristorante
- Sistema autenticazione sicuro (Argon2, sessioni con scadenza 30 giorni)
- Pannello amministratore per gestione clienti
- Recupero password via email
- Diario note per ristorante
- Privacy Policy e Termini di Servizio integrati

---

##  Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Frontend/App | Streamlit |
| Database | Supabase (PostgreSQL) |
| AI | OpenAI GPT-4o-mini |
| Email | Brevo SMTP API |
| Password hashing | Argon2 |
| Hosting | Streamlit Cloud |
| Monitoraggio | GitHub Actions (uptime check ogni 5 min) |

---

##  Avvio locale

```bash
pip install -r requirements-lock.txt
streamlit run app.py
```

Per avere la stessa resa grafica del deploy Railway, usa il lockfile anche in locale.
Il container di produzione installa le dipendenze da requirements-lock.txt.
Su Windows il lockfile esclude automaticamente uvloop, che non e' supportato dalla piattaforma.

---

##  Sicurezza e Backup

### Misure di sicurezza implementate
- Password hash Argon2 (m=65536, t=3)
- Sessioni con scadenza 30 giorni
- Rate limiting login (5 tentativi  blocco 15 min)
- Rate limiting reset password (5 min cooldown)
- Validazione magic bytes su file caricati (PDF, XML, P7M)
- Protezione XSS su dati utente
- Sanitizzazione input AI (anti prompt injection)
- Limite upload: max 100 file / 200 MB per sessione
- Budget giornaliero AI: max 1000 chiamate/giorno
- Rotazione log automatica: 50 MB / 10 backup
- PII rimossi dai log (GDPR Art. 32)
- XSRF protection attiva, CORS disabilitato

### Strategia di Backup

| Componente | Backup | Frequenza |
|---|---|---|
| Database (Supabase) | Point in Time Recovery | Continuo |
| Codice sorgente | Repository Git | Ad ogni commit |
| Dipendenze | requirements-lock.txt | Ad ogni aggiornamento |

---

##  Test

```bash
python -m pytest tests/ -v
```

149 test automatici.

---

##  Licenza

Tutti i diritti riservati  OH YEAH! Hub  2026
