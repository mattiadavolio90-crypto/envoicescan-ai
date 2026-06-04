# MIGRAZIONE APP — Piano switch Streamlit → Next.js

**Creato:** 3 giugno 2026
**Riferimento completo:** `ONEFLUX_MASTER.md` §14-16

---

## Stato attuale

La nuova app Next.js è **funzionalmente completa** (Fasi 0–8 chiuse).
- URL attuale Next.js: `https://nuovo.oneflux.it` (Vercel)
- URL attuale Streamlit: `https://app.oneflux.it` (Railway)
- Database condiviso: entrambi puntano allo stesso Supabase

**Mancano solo:** Fase 9 (test) → Fase 10 (switch DNS) → Fase 11 (spegnimento Streamlit)

---

## Dominio finale

| URL | Destinazione |
|---|---|
| `app.oneflux.it` | Next.js su Vercel (dopo switch) |
| `old.oneflux.it` | Streamlit su Railway (fallback 30 giorni post-switch) |
| `www.oneflux.it` | Tenere libero per landing page pubblica futura |
| `nuovo.oneflux.it` | Redirect → `app.oneflux.it` dopo switch (poi rimuovere) |

**Il link da dare ai clienti oggi:** `https://nuovo.oneflux.it`
**Il link definitivo dopo lo switch:** `https://app.oneflux.it` (stesso che usano già)

---

## Servizi: free vs Pro

| Servizio | Piano attuale | Azione richiesta | Costo post-switch |
|---|---|---|---|
| **Vercel** | Hobby (free) | ⚠️ **Verificare prima dello switch** se `app.oneflux.it` si può aggiungere su Hobby. Se no → upgrade a Pro | €0 → €20/mese |
| **Railway** | Hobby €5/mese | Nessun upgrade. Dopo Fase 11 eliminare solo il servizio Streamlit (non l'intero progetto — FastAPI e queue-worker ci girano) | €5/mese |
| **Supabase** | Free | Nessun upgrade anticipato. Solo se emergono problemi reali (pause inattività, limiti connessioni) | €0 → €25/mese solo se serve |
| **Brevo** | Free (300 email/giorno) | Nessun upgrade | €0 |
| **GitHub Actions** | Free | Nessun upgrade | €0 |
| **OpenAI** | Pay-per-use | Invariato | ~€0,30/cliente/mese |
| **Aruba** | Pagato | Invariato | ~€1/mese |
| **Railway orfano** `exemplary-creation` | Vuoto | **Eliminare** in Fase 11 | risparmio |

**Costo totale stimato post-switch:** ~€26/mese (Vercel Pro + Railway Hobby + OpenAI)

---

## Piano sequenziale

### Fase 9 — Test (prima di toccare qualsiasi DNS)

- [ ] Usare `nuovo.oneflux.it` come cliente reale per almeno 5 giorni
- [ ] Invitare i 2 clienti di test a usare `nuovo.oneflux.it` in parallelo a Streamlit
- [ ] Raccogliere e fixare i bug che emergono
- [ ] Completare la checklist pre-switch qui sotto

### Fase 10 — Switch DNS

- [ ] Verificare se Vercel Hobby supporta dominio custom `app.oneflux.it` → upgrade se necessario
- [ ] Fare backup DB Supabase (snapshot manuale dal dashboard)
- [ ] Avvisare tutti i clienti con almeno 1 settimana di anticipo (messaggio + eventuale video breve)
- [ ] Switch DNS: `app.oneflux.it` → Vercel (Next.js)
- [ ] Creare `old.oneflux.it` → Railway (Streamlit, fallback)
- [ ] Aggiornare data e versione nell'informativa privacy `/privacy` (obbligo GDPR — annotato in MASTER rev.25)
- [ ] Monitorare per almeno 7 giorni

### Fase 11 — Spegnimento Streamlit (30 giorni dopo lo switch, se stabile)

- [ ] Eliminare il servizio Streamlit dal progetto Railway `ingenious-fascination` (lasciare worker FastAPI e queue-worker)
- [ ] Rimuovere `old.oneflux.it` dal DNS Aruba
- [ ] Eliminare il progetto Railway `exemplary-creation` (orfano)
- [ ] Rimuovere `nuovo.oneflux.it` dal DNS (o redirect permanente a `app.oneflux.it`)

---

## Checklist pre-switch (dal MASTER §16)

- [ ] Tutte le sezioni funzionanti e testate su `nuovo.oneflux.it`
- [x] Reset password funzionante lato Next.js (Brevo in produzione)
- [x] Privacy & Cookie Policy + Termini di Servizio pubblicati (`/privacy`, `/termini`)
- [x] Consenso privacy esplicito raccolto all'onboarding con prova reale
- [ ] Aggiornare data/versione informativa al cut-over + allineare lista responsabili
- [ ] Backup DB confermato
- [ ] Clienti avvisati con almeno 1 settimana di anticipo
- [ ] Rollback plan: `old.oneflux.it` → Streamlit pronto

---

## Note importanti

- **Database condiviso**: nessuna migrazione dati. Streamlit e Next.js puntano già allo stesso Supabase. Un dato inserito su uno è visibile sull'altro in tempo reale.
- **Worker FastAPI**: resta su Railway anche dopo lo switch. Non si tocca.
- **Rollback**: se emergono problemi gravi post-switch, basta rimettere il DNS di `app.oneflux.it` su Railway (Streamlit) — i dati sono integri perché il DB è condiviso.
- **`www.oneflux.it`**: non usarlo per l'app. Tenerlo libero per la landing page pubblica futura (presentazione ONEFLUX ai potenziali clienti RECOMA).
